#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
声明侧预检脚本 — 确定性规则检测

在 LLM subagent 审计前运行，从 impl_api.jsonl 的 api_declaration 字段
检测可由纯正则匹配 100% 确定性判定的声明违规。

当前覆盖规则：
  - 5.1.7.8: 数组类型返回值不应联合 null/undefined

输出格式与 raw_findings.json 完全一致（9 个英文字段），
可被 classify_findings.py 正确分类。
"""

import json
import re
import sys
import argparse
from pathlib import Path


# 匹配数组类型联合 null/undefined 的正则
ARRAY_NULLABLE_RE = re.compile(
    r'(?:'
    r'Array<[^>]*>\s*\|\s*(?:null|undefined)'    # Array<T> | null/undefined
    r'|'
    r'\w+\[\]\s*\|\s*(?:null|undefined)'           # T[] | null/undefined
    r')'
)

# 从 api_declaration 提取函数名
API_NAME_RE = re.compile(r'function\s+(\w+)')

# 从 api_declaration 提取返回类型（冒号后到行尾或参数括号）
RETURN_TYPE_RE = re.compile(r'\):\s*(.+)$')

# 预检覆盖的规则 ID
PRECHECK_RULE_ID = '5.1.7.8'


def extract_api_name(api_declaration: str) -> str:
    """从 api_declaration 提取函数名"""
    m = API_NAME_RE.search(api_declaration)
    return m.group(1) if m else ''


def extract_return_type(api_declaration: str) -> str:
    """从 api_declaration 提取返回类型部分"""
    m = RETURN_TYPE_RE.search(api_declaration)
    return m.group(1).strip() if m else ''


def check_array_nullable(return_type: str) -> re.Match | None:
    """检查返回类型是否包含数组类型联合 null/undefined"""
    return ARRAY_NULLABLE_RE.search(return_type)


def derive_component(module_name: str) -> str:
    """从 module_name 推导 component 名称"""
    name = module_name
    if name.startswith('@ohos.'):
        name = name[len('@ohos.'):]
    elif name.startswith('@'):
        name = name[1:]
    return name.replace('.', '_')


def load_rules(rules_path: str) -> dict:
    """加载 active_rules.json，返回 {id: rule} 字典"""
    with open(rules_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    rules_list = data if isinstance(data, list) else data.get('rules', [])
    return {r['id']: r for r in rules_list if 'id' in r}


def process_impl_api(impl_api_path: str, rule: dict) -> tuple[list, int, int]:
    """
    处理 impl_api.jsonl，返回 (findings, total_count, skipped_count)
    """
    findings = []
    total = 0
    skipped = 0

    rule_description = rule.get('description', '')

    with open(impl_api_path, 'r', encoding='utf-8') as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                api = json.loads(line)
            except json.JSONDecodeError:
                print(f'[precheck] Warning: line {line_no} is not valid JSON, skipping',
                      file=sys.stderr)
                skipped += 1
                continue

            total += 1

            api_declaration = api.get('api_declaration', '')
            if not api_declaration:
                skipped += 1
                continue

            # 提取返回类型
            return_type = extract_return_type(api_declaration)
            if not return_type:
                continue

            # 检查数组类型联合空值
            match = check_array_nullable(return_type)
            if not match:
                continue

            # 提取 API 名称
            api_name = extract_api_name(api_declaration)
            if not api_name:
                skipped += 1
                continue

            # 提取 component
            impl_repo_path = api.get('impl_repo_path', '')
            component = impl_repo_path if impl_repo_path else derive_component(
                api.get('module_name', '')
            )

            # 提取声明文件路径
            declaration_file = api.get('declaration_file', '')

            # 构造 finding
            finding = {
                'rule_id': PRECHECK_RULE_ID,
                'rule_description': rule_description,
                'finding_description': (
                    f'{api_name} 返回值类型 {return_type} 中数组类型联合了 '
                    f'null/undefined，空场景应返回空数组而非 null/undefined'
                ),
                'evidence': [
                    {
                        'file': declaration_file,
                        'line': 1,
                        'snippet': api_declaration
                    }
                ],
                'component': component,
                'affected_apis': [api_name],
                'modification_suggestion': (
                    f'移除 {api_name} 返回类型中的 | null / | undefined，'
                    f'空场景应返回空数组 []'
                ),
                'severity_level': '中',
                'affected_error_codes': ''
            }
            findings.append(finding)

    return findings, total, skipped


def main():
    parser = argparse.ArgumentParser(
        description='声明侧预检脚本 — 确定性规则检测'
    )
    parser.add_argument(
        'impl_api', help='impl_api.jsonl 文件路径'
    )
    parser.add_argument(
        'rules', help='active_rules.json 文件路径'
    )
    parser.add_argument(
        '-o', '--output', default='precheck_findings.json',
        help='输出文件路径 (默认: precheck_findings.json)'
    )
    args = parser.parse_args()

    # 加载规则
    rules = load_rules(args.rules)
    if PRECHECK_RULE_ID not in rules:
        print(f'[precheck] Warning: rule {PRECHECK_RULE_ID} not found in '
              f'{args.rules}, skipping precheck', file=sys.stderr)
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump({'findings': [], 'precheck_summary': {
                'total_apis': 0, 'findings_count': 0,
                'rules_checked': []
            }}, f, ensure_ascii=False, indent=2)
        return

    rule = rules[PRECHECK_RULE_ID]

    # 处理 API 列表
    findings, total, skipped = process_impl_api(args.impl_api, rule)

    # 写入输出
    result = {
        'findings': findings,
        'precheck_summary': {
            'total_apis': total,
            'findings_count': len(findings),
            'rules_checked': [PRECHECK_RULE_ID]
        }
    }

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f'[precheck] Checked {total} APIs, found {len(findings)} violations '
          f'for rule {PRECHECK_RULE_ID}')
    if skipped > 0:
        print(f'[precheck] Skipped {skipped} APIs (missing fields or parse errors)')


if __name__ == '__main__':
    main()
