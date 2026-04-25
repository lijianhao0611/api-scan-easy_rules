#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审计输出验证脚本 (api-level-scan 版)
验证 api-level-scan 输出的格式合规性、完整性和一致性
支持 JSONL 发现文件和调用链 JSON 文件的验证
"""

import os
import json
import argparse
import re
from typing import List, Dict, Tuple
from pathlib import Path


# JSONL 每行必需的字段
REQUIRED_JSONL_FIELDS = [
    "kit", "部件", "编号", "问题描述", "发现详情说明",
    "代码文件", "代码行位置", "受影响的api", "api声明",
    "声明文件位置", "修改建议", "问题严重等级", "影响的错误码"
]

# 合法的严重等级
VALID_SEVERITY_LEVELS = ["严重", "高", "中", "低"]

# 评分类残留字段（不应出现在输出中）
SCORING_FIELDS = [
    "score", "weight", "rating", "deduct", "grade",
    "final_score", "base_score", "max_score",
    "level2", "level3", "issue_type_2", "issue_type_3"
]

# 必需的输出文件
REQUIRED_FILES = [
    "api_scan_findings.jsonl",
    "api_call_chains.json",
    "api_scan_summary.md"
]


class ValidationResult:
    """验证结果"""
    def __init__(self):
        self.passed = True
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def add_error(self, message: str):
        self.passed = False
        self.errors.append(message)

    def add_warning(self, message: str):
        self.warnings.append(message)

    def print_report(self):
        if self.passed:
            print("✅ 所有验证通过")
        else:
            print("❌ 验证失败")

        if self.errors:
            print("\n错误:")
            for error in self.errors:
                print(f"  - {error}")

        if self.warnings:
            print("\n警告:")
            for warning in self.warnings:
                print(f"  - {warning}")


def load_rules(rules_path: str) -> Dict[str, Dict]:
    """加载规则集构建查找字典"""
    with open(rules_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    rules_map = {}
    for rule in data.get("rules", []):
        rule_id = rule.get("id", "")
        if rule_id:
            rules_map[rule_id] = rule
    return rules_map


def validate_jsonl_findings(output_dir: str, rules_map: Dict[str, Dict]) -> ValidationResult:
    """验证 api_scan_findings.jsonl 文件"""
    result = ValidationResult()

    jsonl_path = os.path.join(output_dir, "api_scan_findings.jsonl")
    if not os.path.exists(jsonl_path):
        result.add_error("未找到 api_scan_findings.jsonl 文件")
        return result

    lines = []
    try:
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
    except Exception as e:
        result.add_error(f"读取 api_scan_findings.jsonl 失败: {e}")
        return result

    if not lines:
        result.add_warning("api_scan_findings.jsonl 为空（无任何发现）")
        return result

    seen_keys = set()

    for line_num, line in enumerate(lines, 1):
        # 1. JSON 解析
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            result.add_error(f"JSONL 第 {line_num} 行 JSON 解析失败: {e}")
            continue

        if not isinstance(obj, dict):
            result.add_error(f"JSONL 第 {line_num} 行不是 JSON 对象")
            continue

        # 2. 必需字段检查
        for field in REQUIRED_JSONL_FIELDS:
            if field not in obj:
                result.add_error(f"JSONL 第 {line_num} 行缺少必需字段: {field}")

        # 3. 规则存在性检查
        rule_id = obj.get("编号", "")
        if rule_id and rules_map:
            if rule_id not in rules_map:
                result.add_error(f"JSONL 第 {line_num} 行的规则编号 '{rule_id}' 不在有效规则集中")

        # 4. 代码文件/代码行位置格式检查（逗号分隔，一一对应）
        code_files = obj.get("代码文件", "")
        code_lines = obj.get("代码行位置", "")
        if code_files:
            file_list = [f.strip() for f in str(code_files).split(",")]
            line_list = [l.strip() for l in str(code_lines).split(",")]
            if len(file_list) != len(line_list):
                result.add_error(
                    f"JSONL 第 {line_num} 行的代码文件({len(file_list)}个)与"
                    f"代码行位置({len(line_list)}个)数量不匹配"
                )
            for i, line_val in enumerate(line_list):
                if line_val != "NA":
                    try:
                        if int(line_val) <= 0:
                            result.add_error(f"JSONL 第 {line_num} 行代码行位置[{i}] 无效: {line_val}")
                    except ValueError:
                        result.add_error(f"JSONL 第 {line_num} 行代码行位置[{i}] 不是数字也不是 NA: {line_val}")

        # 5. 严重等级检查
        severity = obj.get("问题严重等级", "")
        if severity and severity not in VALID_SEVERITY_LEVELS:
            result.add_error(
                f"JSONL 第 {line_num} 行的问题严重等级 '{severity}' 不合法，"
                f"应为: {', '.join(VALID_SEVERITY_LEVELS)}"
            )

        # 6. 修改建议非空检查
        suggestion = obj.get("修改建议", "")
        if not suggestion or not str(suggestion).strip():
            result.add_error(f"JSONL 第 {line_num} 行的修改建议为空")

        # 7. 影响的错误码格式检查
        error_codes = obj.get("影响的错误码", "")
        if error_codes:
            for code in str(error_codes).split(","):
                code = code.strip()
                if code and not re.match(r'^\d+$', code):
                    result.add_error(f"JSONL 第 {line_num} 行的影响的错误码 '{code}' 不是纯数字")

        # 8. 去重检查（同一规则 + 同一 API 应只有一条记录）
        dedup_key = (rule_id, obj.get("受影响的api", ""))
        if dedup_key in seen_keys:
            result.add_error(f"JSONL 第 {line_num} 行重复（同一规则 '{rule_id}' + 同一 API '{obj.get('受影响的api', '')}' 应合并为一条）")
        else:
            seen_keys.add(dedup_key)

    return result


def validate_call_chains(output_dir: str) -> ValidationResult:
    """验证 api_call_chains.json 文件"""
    result = ValidationResult()

    chains_path = os.path.join(output_dir, "api_call_chains.json")
    if not os.path.exists(chains_path):
        result.add_error("未找到 api_call_chains.json 文件")
        return result

    try:
        with open(chains_path, 'r', encoding='utf-8') as f:
            chains = json.load(f)
    except json.JSONDecodeError as e:
        result.add_error(f"api_call_chains.json JSON 解析失败: {e}")
        return result

    if not isinstance(chains, list):
        result.add_error("api_call_chains.json 顶层应为 JSON 数组")
        return result

    for i, chain in enumerate(chains):
        if not isinstance(chain, dict):
            result.add_error(f"调用链 #{i+1} 不是 JSON 对象")
            continue

        # 检查必需字段
        for field in ["api_name", "api_declaration", "module_name", "call_chain"]:
            if field not in chain:
                result.add_error(f"调用链 #{i+1} (api: {chain.get('api_name', '?')}) 缺少字段: {field}")

        # 递归检查 call_chain 结构（树形，无深度限制）
        call_chain = chain.get("call_chain", [])
        if not isinstance(call_chain, list):
            result.add_error(f"调用链 #{i+1} 的 call_chain 不是数组")
            continue

        def validate_call_node(node, path):
            """递归验证调用节点"""
            if not isinstance(node, dict):
                result.add_error(f"调用链 #{i+1} {path} 不是对象")
                return

            for field in ["function_name", "file", "line"]:
                if field not in node:
                    result.add_warning(f"调用链 #{i+1} {path} 缺少字段: {field}")

            calls = node.get("calls", [])
            if not isinstance(calls, list):
                result.add_error(f"调用链 #{i+1} {path}.calls 不是数组")
                return

            for k, child in enumerate(calls):
                validate_call_node(child, f"{path}.calls[{k}]")

        for j, node in enumerate(call_chain):
            validate_call_node(node, f"call_chain[{j}]")

    return result


def validate_file_completeness(output_dir: str) -> ValidationResult:
    """验证输出文件完整性"""
    result = ValidationResult()

    if not os.path.isdir(output_dir):
        result.add_error(f"输出目录不存在: {output_dir}")
        return result

    existing_files = set(os.listdir(output_dir))

    for required in REQUIRED_FILES:
        if required not in existing_files:
            result.add_error(f"缺少必需文件: {required}")

    return result


def validate_all(output_dir: str, rules_path: str = None) -> Tuple[bool, List[str], List[str]]:
    """运行所有验证"""
    all_errors = []
    all_warnings = []

    # 加载规则集
    rules_map = {}
    if rules_path and os.path.exists(rules_path):
        try:
            rules_map = load_rules(rules_path)
        except Exception as e:
            all_warnings.append(f"无法加载规则集: {e}")

    # 1. 验证 JSONL 发现文件
    result = validate_jsonl_findings(output_dir, rules_map)
    all_errors.extend(result.errors)
    all_warnings.extend(result.warnings)

    # 2. 验证调用链 JSON
    result = validate_call_chains(output_dir)
    all_errors.extend(result.errors)
    all_warnings.extend(result.warnings)

    # 3. 验证文件完整性
    result = validate_file_completeness(output_dir)
    all_errors.extend(result.errors)
    all_warnings.extend(result.warnings)

    passed = len(all_errors) == 0
    return passed, all_errors, all_warnings


def main():
    parser = argparse.ArgumentParser(
        description="验证 api-level-scan 审计输出的格式合规性和完整性"
    )
    parser.add_argument("output_dir", help="审计输出目录路径")
    parser.add_argument("--rules", help="有效规则集 JSON 路径 (active_rules.json)")

    args = parser.parse_args()

    print(f"🔍 验证目录: {args.output_dir}")
    if args.rules:
        print(f"📋 规则集: {args.rules}")
    print()

    passed, errors, warnings = validate_all(args.output_dir, args.rules)

    if passed:
        print("✅ 所有验证通过")
    else:
        print("❌ 验证失败")

    if errors:
        print(f"\n错误 ({len(errors)}):")
        for error in errors:
            print(f"  - {error}")

    if warnings:
        print(f"\n警告 ({len(warnings)}):")
        for warning in warnings:
            print(f"  - {warning}")

    print(f"\n统计: {len(errors)} 错误, {len(warnings)} 警告")
    return 0 if passed else 1


if __name__ == "__main__":
    exit(main())
