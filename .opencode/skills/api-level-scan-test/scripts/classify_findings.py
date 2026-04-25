#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
发现分类脚本 (api-level-scan 版)
验证每个发现的 rule_id 是否在 active_rules.json 中存在，并进行字段完整性检查
适配 JSONL 格式输出，新增 affected_error_codes 字段验证
"""

import json
import argparse
import re
from pathlib import Path
from typing import Dict, List, Tuple


# 每个 finding 必需的字段（api-level-scan 版本）
REQUIRED_FINDING_FIELDS = [
    "rule_id", "rule_description", "finding_description",
    "evidence", "component", "affected_apis",
    "modification_suggestion", "severity_level",
    "affected_error_codes"
]

# 合法的严重等级
VALID_SEVERITY_LEVELS = ["严重", "高", "中", "低"]


def load_rules(rules_path: str) -> Dict[str, Dict]:
    """加载规则并构建 id -> rule 的查找字典"""
    with open(rules_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    rules_map = {}
    for rule in data.get("rules", []):
        rule_id = rule.get("id", "")
        if rule_id:
            rules_map[rule_id] = rule

    return rules_map


def load_findings(findings_path: str) -> List[Dict]:
    """加载原始发现"""
    with open(findings_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 支持两种格式：直接数组或 {findings: [...]}
    if isinstance(data, list):
        return data
    return data.get("findings", [])


def validate_error_codes(error_codes_str: str) -> List[str]:
    """验证 affected_error_codes 格式：应为逗号分隔数字或空字符串"""
    issues = []
    if error_codes_str == "":
        return issues  # 空字符串合法

    codes = error_codes_str.split(",")
    for code in codes:
        code = code.strip()
        if not code:
            issues.append(f"影响的错误码包含空段: '{error_codes_str}'")
        elif not re.match(r'^\d+$', code):
            issues.append(f"影响的错误码 '{code}' 不是纯数字")

    return issues


def classify_findings(raw_findings: List[Dict],
                      rules_map: Dict[str, Dict]) -> Tuple[List[Dict], List[Dict]]:
    """
    分类和验证发现

    Returns:
        (classified_findings, unclassified_findings)
    """
    classified = []
    unclassified = []
    seen_keys = set()

    for i, finding in enumerate(raw_findings):
        issues = []
        rule_id = finding.get("rule_id", "")

        # 检查必需字段
        for field in REQUIRED_FINDING_FIELDS:
            if field not in finding:
                issues.append(f"缺少必需字段: {field}")

        if issues:
            finding["_classification_issues"] = issues
            if not rule_id:
                finding["rule_id"] = f"UNCLASSIFIED-{i+1}"
            unclassified.append(finding)
            continue

        # 检查 rule_id 是否在规则集中
        if not rule_id:
            issues.append("rule_id 为空")
        elif rule_id not in rules_map:
            issues.append(f"rule_id '{rule_id}' 不在有效规则集中")

        # 检查 evidence 格式
        evidence = finding.get("evidence", [])
        if not isinstance(evidence, list):
            issues.append("evidence 不是数组")
        else:
            for j, ev in enumerate(evidence):
                if isinstance(ev, dict):
                    if not ev.get("file"):
                        issues.append(f"evidence[{j}] 缺少 file")
                    if not ev.get("line") or ev.get("line", 0) <= 0:
                        issues.append(f"evidence[{j}] line 无效")
                else:
                    issues.append(f"evidence[{j}] 不是对象")

        # 检查 affected_error_codes 格式
        error_codes = finding.get("affected_error_codes", "")
        code_issues = validate_error_codes(error_codes)
        issues.extend(code_issues)

        # 检查 severity_level
        severity = finding.get("severity_level", "")
        if not severity:
            issues.append("severity_level 为空")
        elif severity not in VALID_SEVERITY_LEVELS:
            issues.append(f"severity_level '{severity}' 不是有效值，应为: {', '.join(VALID_SEVERITY_LEVELS)}")

        # 检查 modification_suggestion
        suggestion = finding.get("modification_suggestion", "")
        if not suggestion or not suggestion.strip():
            issues.append("modification_suggestion 为空")

        # 去重检查（按 rule_id + affected_api 去重，同一规则同一 API 只应有一条记录）
        affected_api = finding.get("affected_apis", [""])[0] if finding.get("affected_apis") else ""
        dedup_key = (rule_id, affected_api)
        if dedup_key in seen_keys:
            issues.append(f"重复的发现（同一规则 '{rule_id}' + 同一 API '{affected_api}' 存在多条记录，应合并为一条）")
        else:
            seen_keys.add(dedup_key)

        # 补充 rule_description（如果缺失或不一致）
        if rule_id in rules_map:
            expected_desc = rules_map[rule_id].get("description", "")
            actual_desc = finding.get("rule_description", "")
            if actual_desc != expected_desc and expected_desc:
                finding["rule_description"] = expected_desc

        if issues:
            finding["_classification_issues"] = issues
            unclassified.append(finding)
        else:
            classified.append(finding)

    return classified, unclassified


def main():
    parser = argparse.ArgumentParser(
        description="验证和分类审计发现 (api-level-scan 版)"
    )
    parser.add_argument("findings", help="原始发现 JSON 文件路径")
    parser.add_argument("--rules", required=True,
                        help="有效规则集 JSON 路径 (active_rules.json)")
    parser.add_argument("-o", "--output", help="分类后输出路径")

    args = parser.parse_args()

    rules_map = load_rules(args.rules)
    raw_findings = load_findings(args.findings)

    classified, unclassified = classify_findings(raw_findings, rules_map)

    # 构建输出
    result = {
        "metadata": {
            "total_findings": len(raw_findings),
            "classified_count": len(classified),
            "unclassified_count": len(unclassified),
            "rules_available": len(rules_map)
        },
        "findings": classified,
        "unclassified": unclassified
    }

    # 确定输出路径
    output_path = args.output
    if not output_path:
        output_path = str(Path(args.findings).parent / "classified_findings.json")

    out_dir = Path(output_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 打印统计
    print(f"发现分类统计:")
    print(f"  原始发现数: {len(raw_findings)}")
    print(f"  已分类数: {len(classified)}")
    print(f"  未分类数: {len(unclassified)}")

    if unclassified:
        print(f"\n未分类发现的问题:")
        for finding in unclassified:
            issues = finding.get("_classification_issues", [])
            rule_id = finding.get("rule_id", "?")
            print(f"  - {rule_id}: {'; '.join(issues)}")

    print(f"\n输出: {output_path}")

    return 1 if unclassified else 0


if __name__ == "__main__":
    exit(main())
