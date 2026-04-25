#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
规则过滤脚本
从 config/rule.json 中过滤掉评分类规则条目，输出有效规则集和被忽略规则集
"""

import json
import argparse
from pathlib import Path
from typing import List, Dict, Tuple


# 评分类关键词（不区分大小写匹配 rule.id 和 rule.description）
SCORING_KEYWORDS = [
    "score", "weight", "扣分", "权重", "致命问题", "严重问题", "一般问题",
    "提示问题", "rating", "points", "deduct", "grading", "评分", "得分", "计分",
    "等级评定", "分值"
]

# 从保留规则中移除的评分字段
SCORING_FIELDS_TO_REMOVE = [
    "score", "weight", "max_score", "base_score",
    "level2_weight", "level3_weight",
    "deduction", "penalty",
    "grade_level", "grade_description"
]


def is_scoring_rule(rule: Dict) -> bool:
    """判断规则是否为评分类规则"""
    rule_id = str(rule.get("id", "")).lower()
    description = str(rule.get("description", "")).lower()

    for keyword in SCORING_KEYWORDS:
        kw = keyword.lower()
        if kw in rule_id or kw in description:
            return True
    return False


def remove_scoring_fields(rule: Dict) -> Dict:
    """从规则中移除评分类字段"""
    cleaned = dict(rule)
    for field in SCORING_FIELDS_TO_REMOVE:
        cleaned.pop(field, None)
    return cleaned


def filter_rules(input_path: str, output_path: str = None,
                 ignored_path: str = None) -> Tuple[List[Dict], List[Dict]]:
    """
    过滤评分类规则

    Returns:
        (active_rules, ignored_rules)
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    rules = data.get("rules", [])

    active_rules = []
    ignored_rules = []

    for rule in rules:
        if is_scoring_rule(rule):
            ignored_rules.append(rule)
        else:
            active_rules.append(remove_scoring_fields(rule))

    # 输出有效规则
    active_data = {"rules": active_rules}
    if output_path:
        out_dir = Path(output_path).parent
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(active_data, f, ensure_ascii=False, indent=2)
        print(f"有效规则已写入: {output_path}")
    else:
        print(json.dumps(active_data, ensure_ascii=False, indent=2))

    # 输出被忽略规则
    if ignored_path:
        ignored_data = {"rules": ignored_rules}
        ign_dir = Path(ignored_path).parent
        ign_dir.mkdir(parents=True, exist_ok=True)
        with open(ignored_path, 'w', encoding='utf-8') as f:
            json.dump(ignored_data, f, ensure_ascii=False, indent=2)
        print(f"被忽略规则已写入: {ignored_path}")

    # 打印统计
    print(f"\n规则过滤统计:")
    print(f"  原始规则数: {len(rules)}")
    print(f"  过滤规则数: {len(ignored_rules)}")
    print(f"  有效规则数: {len(active_rules)}")

    if ignored_rules:
        print(f"\n被过滤的规则:")
        for rule in ignored_rules:
            rid = rule.get("id", "?")
            desc = rule.get("description", "")[:60]
            print(f"  - {rid}: {desc}...")

    return active_rules, ignored_rules


def main():
    parser = argparse.ArgumentParser(
        description="过滤 rule.json 中的评分类规则"
    )
    parser.add_argument("input", help="输入 rule.json 路径")
    parser.add_argument("-o", "--output", help="有效规则输出路径")
    parser.add_argument("--ignored", help="被忽略规则输出路径")

    args = parser.parse_args()

    output = args.output
    if not output:
        # 默认输出到同目录下的 active_rules.json
        output = str(Path(args.input).parent / "active_rules.json")

    ignored = args.ignored
    if not ignored:
        ignored = str(Path(output).parent / "ignored_rules.json")

    active, ignored_list = filter_rules(args.input, output, ignored)

    return 0 if active else 1


if __name__ == "__main__":
    exit(main())
