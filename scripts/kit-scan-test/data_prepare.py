"""
data_prepare.py - API 数据准备模块

负责 JSONL 文件读写、数据合并和 XLSX 转换。
不调用 CLI，仅处理数据流。
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple

import sys; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts_logger import get_logger

logger = get_logger("data_prepare")


# Windows 路径字段名列表（这些字段可能包含文件路径）
PATH_FIELDS = [
    "napi_file_path", "declaration_file", "NAPI_map_file",
    "Framework_decl_file", "impl_file_path", "impl_repo_path",
    "framework_header_path", "impl_cpp_path", "napi_file",
    "framework_file", "impl_file", "js_doc"
]


def _sanitize_json_line(line: str) -> str:
    """
    处理 JSON 行中的无效转义序列。
    将 Windows 路径中的单反斜杠转换为正斜杠。

    处理模式: "field": "X:/path" (将反斜杠转为正斜杠)
    """
    # 简化策略: 使用正则找到所有字符串值，转换其中的反斜杠为正斜杠
    # 模式: "key": "value"
    pattern = r'"([^"]+)":\s*"([^"]*)"'

    def replace_backslash_in_paths(match):
        key = match.group(1)
        value = match.group(2)
        # 只处理路径相关的字段或明显是路径的内容
        is_path_field = key in PATH_FIELDS
        looks_like_path = value and "\\" in value and (
            "workspace" in value.lower() or
            "repo" in value.lower() or
            (len(value) >= 2 and value[0].isalpha() and value[1] == ":")
        )
        if is_path_field or looks_like_path:
            value = value.replace("\\", "/")
        return f'"{key}": "{value}"'

    return re.sub(pattern, replace_backslash_in_paths, line)


def load_jsonl_line(line: str) -> Dict[str, Any]:
    """
    安全解析一行 JSONL，自动处理 Windows 路径中的无效转义。

    Args:
        line: JSONL 文件的一行

    Returns:
        解析后的字典

    Raises:
        JSONDecodeError: 如果处理后仍无法解析
    """
    line = line.strip()
    if not line:
        raise json.JSONDecodeError("Empty line", line, 0)

    # 先尝试直接解析
    try:
        return json.loads(line)
    except json.JSONDecodeError as e:
        if "escape" in str(e).lower():
            # 处理无效转义
            sanitized = _sanitize_json_line(line)
            try:
                record = json.loads(sanitized)
                logger.debug("已修复无效转义序列: %s", line[:50])
                return record
            except json.JSONDecodeError as e2:
                logger.error("无法解析 JSON 行: %s", line[:100])
                raise e2
        raise


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
            record = load_jsonl_line(line)
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
            record = load_jsonl_line(line)
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
            records.append(load_jsonl_line(line))

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
