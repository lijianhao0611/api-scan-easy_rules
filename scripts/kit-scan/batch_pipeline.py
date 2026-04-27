"""
batch_pipeline.py - 批量 API 数据处理模块

负责 JSONL 文件读写、数据分批、prompt 构建和结果合并。
不调用 CLI，仅处理数据流。
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Tuple

import sys; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts_logger import get_logger

logger = get_logger("batch_pipeline")

# 每个 batch 审计完成后，结果文件名
RESULT_FILENAME: str = "api_scan_findings.jsonl"


def load_and_split_impl_api(
    impl_api_path: Path,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    读取 impl_api.jsonl，分离 impl_api_name 为空和不为空的数据。

    Returns:
        (empty_impl_list, non_empty_impl_list)
    """
    empty_list: List[Dict[str, Any]] = []
    non_empty_list: List[Dict[str, Any]] = []

    with open(impl_api_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("impl_api_name", "") == "":
                empty_list.append(record)
            else:
                non_empty_list.append(record)

    logger.info(
        "读取 impl_api.jsonl 完成: impl_api_name 为空 %d 条, 不为空 %d 条",
        len(empty_list), len(non_empty_list),
    )
    return empty_list, non_empty_list


def load_matching_api_data(
    api_path: Path, empty_impl_list: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    读取 api.jsonl，匹配 impl_api_name 为空的数据对应的条目。
    使用 api_declaration + module_name + declaration_file 三字段联合匹配。
    """
    match_keys = set()
    for record in empty_impl_list:
        key = (
            record.get("api_declaration", ""),
            record.get("module_name", ""),
            record.get("declaration_file", ""),
        )
        match_keys.add(key)

    matched: List[Dict[str, Any]] = []
    with open(api_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            key = (
                record.get("api_declaration", ""),
                record.get("module_name", ""),
                record.get("declaration_file", ""),
            )
            if key in match_keys:
                matched.append(record)

    logger.info(
        "从 api.jsonl 匹配到 %d 条数据 (待匹配 %d 条)",
        len(matched), len(empty_impl_list),
    )
    return matched


def prepare_batches(
    non_empty_impl: List[Dict[str, Any]],
    matched_api: List[Dict[str, Any]],
    batch_size: int,
    output_dir: Path,
) -> List[Path]:
    """
    合并数据、按 batch_size 分组，并将每批写入独立的 JSONL 文件。

    输出到 {output_dir}/batch_result/input/batch_0.jsonl, batch_1.jsonl, ...

    Returns:
        所有 batch 文件路径列表
    """
    all_data = non_empty_impl + matched_api

    input_dir = output_dir / "batch_result" / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    batch_paths: List[Path] = []
    for i in range(0, len(all_data), batch_size):
        batch = all_data[i : i + batch_size]
        batch_path = input_dir / f"batch_{i // batch_size}.jsonl"
        with open(batch_path, "w", encoding="utf-8") as f:
            for record in batch:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        batch_paths.append(batch_path)
        logger.info("写入 batch %d: %d 条 API -> %s", i // batch_size, len(batch), batch_path)

    logger.info("共 %d 条数据, 分为 %d 个 batch (batch_size=%d)", len(all_data), len(batch_paths), batch_size)
    return batch_paths


def build_scan_prompt(
    batch_input_path: Path, batch_out_dir: Path, repo_base: Path
) -> str:
    """
    为单个 batch 构建 /api-level-scan 的 prompt。
    使用文件路径引用而非嵌入 JSONL 数据。
    """

    prompt = (
        f"/api-level-scan\t"
        f"api_input={batch_input_path}\t"
        f"repo_base={repo_base}\t"
        f"out_path={batch_out_dir}\t"

    )
    if batch_out_dir.parent/'api_extraction_report.md' in batch_out_dir.parent.iterdir():
        prompt += "api_extraction_report_path={}\n".format(batch_out_dir.parent/'api_extraction_report.md')
        logger.info("已存在 api_extraction_report.md，已将相关知识路径注入")
    return prompt


def collect_batch_result_dirs(output_dir: Path) -> List[Path]:
    """
    扫描 {output_dir}/batch_result/ 下所有匹配 batch_{i} 模式的目录，
    按编号排序返回。
    """
    batch_result_dir = output_dir / "batch_result"
    if not batch_result_dir.exists():
        return []

    dirs: List[Path] = []
    for p in sorted(batch_result_dir.iterdir()):
        if p.is_dir() and p.name.startswith("batch_") and p.name != "input":
            dirs.append(p)
    return dirs


def merge_batch_results(output_dir: Path, output_path: Path) -> int:
    """
    自动扫描 batch_result 下所有 batch 目录，将每个目录下的
    api_scan/api_scan_findings.jsonl 合并为一个文件。
    """
    batch_dirs = collect_batch_result_dirs(output_dir)
    if not batch_dirs:
        logger.warning("未找到任何 batch 结果目录")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_lines = 0
    with open(output_path, "w", encoding="utf-8") as out_f:
        for dir_path in batch_dirs:
            result_file = dir_path / "api_scan" / RESULT_FILENAME
            if not result_file.exists():
                logger.info("跳过: 结果文件不存在: %s", result_file)
                continue

            with open(result_file, "r", encoding="utf-8") as in_f:
                for line in in_f:
                    line = line.strip()
                    if not line:
                        continue
                    out_f.write(line + "\n")
                    total_lines += 1

    logger.info("合并完成: %d 条记录 -> %s", total_lines, output_path)
    return total_lines


def jsonl_to_xlsx(jsonl_path: Path, xlsx_path: Path) -> int:
    """
    将 JSONL 文件转为 XLSX 表格。
    逐行读取 JSONL，以第一行的所有 key 作为表头，每行数据写入一行。
    """
    from openpyxl import Workbook

    records: List[Dict[str, Any]] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))

    if not records:
        logger.info("JSONL 文件为空，跳过 XLSX 生成: %s", jsonl_path)
        return 0

    # 收集所有 key（保持首次出现的顺序）
    seen: set = set()
    headers: List[str] = []
    for rec in records:
        for k in rec:
            if k not in seen:
                seen.add(k)
                headers.append(k)

    wb = Workbook()
    ws = wb.active
    ws.title = "audit_results"
    ws.append(headers)

    for rec in records:
        ws.append([rec.get(h, "") for h in headers])

    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(xlsx_path))
    logger.info("XLSX 已生成: %s (%d 行)", xlsx_path, len(records))
    return len(records)
