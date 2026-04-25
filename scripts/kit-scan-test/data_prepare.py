"""
data_prepare.py - API 数据准备模块

负责 JSONL 文件读写、数据合并和 XLSX 转换。
不调用 CLI，仅处理数据流。
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Tuple

import sys; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts_logger import get_logger

logger = get_logger("data_prepare")


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


def prepare_merged_input(
    non_empty_impl: List[Dict[str, Any]],
    matched_api: List[Dict[str, Any]],
    output_dir: Path,
) -> Path:
    """
    合并 Format 1（有完整 impl 路径）和 Format 2（有 js_doc）数据，
    写入单个 JSONL 文件供 api-level-scan-test 技能使用。

    Returns:
        合并后的 JSONL 文件路径
    """
    merged_path = output_dir / "merged_input.jsonl"
    all_data = non_empty_impl + matched_api

    with open(merged_path, "w", encoding="utf-8") as f:
        for record in all_data:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    logger.info(
        "合并完成: 共 %d 条 API -> %s", len(all_data), merged_path,
    )
    logger.info(
        "  Format 1 (有 impl 路径): %d 条", len(non_empty_impl),
    )
    logger.info(
        "  Format 2 (有 js_doc):    %d 条", len(matched_api),
    )
    return merged_path


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
