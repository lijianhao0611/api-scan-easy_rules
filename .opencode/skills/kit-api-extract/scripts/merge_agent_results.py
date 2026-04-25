#!/usr/bin/env python3
"""将 agent 返回的结果合并到 impl_api.jsonl"""
import json
import sys


def _norm_decl(decl: str) -> str:
    """标准化 API 声明：collapse 连续空格 + strip，用于匹配。"""
    return ' '.join(decl.split())


def merge_results(impl_jsonl_path: str, agent_results_json: str):
    # 读取现有数据，按 标准化后的api_declaration+module_name 做索引
    records = {}
    order = []
    with open(impl_jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            r = json.loads(line.strip())
            key = (_norm_decl(r['api_declaration']), r['module_name'])
            records[key] = r
            order.append(key)

    # 解析 agent 结果
    # agent 结果是 JSON 数组格式
    updated = 0
    new_records = []

    # 尝试从文本中提取 JSON 数组
    agent_data = json.loads(agent_results_json)
    if isinstance(agent_data, list):
        for r in agent_data:
            key = (_norm_decl(r['api_declaration']), r['module_name'])
            if key in records:
                # 合并：agent 结果优先
                records[key].update(r)
                updated += 1
            else:
                records[key] = r
                order.append(key)
                new_records.append(key)

    # 写回
    with open(impl_jsonl_path, 'w', encoding='utf-8') as f:
        for key in order:
            f.write(json.dumps(records[key], ensure_ascii=False) + '\n')

    print(f"合并完成: 更新 {updated} 条, 新增 {len(new_records)} 条")
    return updated

if __name__ == '__main__':
    impl_path = sys.argv[1]
    agent_json_path = sys.argv[2]
    with open(agent_json_path, 'r', encoding='utf-8') as f:
        agent_json = f.read()
    merge_results(impl_path, agent_json)
