#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
C API 实现文件映射脚本。

从 api.jsonl 中筛选 api_type="c" 的记录，通过 @library 标签和 BUILD.gn 分析，
确定性映射 C API 函数到源代码实现文件。

映射链路:
  @library (.so 名) → DataBases 中 BUILD.gn 的 ohos_shared_library 目标 → sources 列表 →
  grep OH_* 函数名匹配 .cpp/.c 实现文件

用法:
    python3 extract_c_impl_map.py --api_jsonl <api.jsonl> --databases <DataBases_dir> -o <output_dir>

输出:
    更新 api.jsonl，填充 impl_repo_path, impl_file_path, Framework_decl_file 字段。
    同时输出 c_impl_map.json 供 Phase 3 Agent 参考。
"""

import argparse
import json
import re
import sys
from pathlib import Path


# 排除的目录模式（测试、示例、文档）
EXCLUDE_DIRS = {'test', 'unittest', 'fuzztest', 'fuzz', 'example', 'demo', 'docs'}

# 实现文件扩展名优先级
IMPL_EXTENSIONS = {'.cpp', '.c'}
HEADER_EXTENSIONS = {'.h'}


def load_api_records(api_jsonl_path):
    """加载 api.jsonl 中的 C API 记录。"""
    records = []
    with open(api_jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get('api_type') == 'c':
                records.append(rec)
    return records


def extract_function_name(api_declaration):
    """从 API 声明中提取函数名。"""
    m = re.search(r'\b((?:OH|OHOS)_\w+)\s*\(', api_declaration)
    if m:
        return m.group(1)
    return None


def find_library_in_build_gn(build_gn_path):
    """从 BUILD.gn 中提取 ohos_shared_library 目标及其 output_name / sources。

    返回 list of {name, output_name, sources}
    """
    try:
        content = Path(build_gn_path).read_text(encoding='utf-8', errors='replace')
    except Exception:
        return []

    targets = []
    # 匹配 ohos_shared_library("name") { ... }
    for m in re.finditer(r'ohos_shared_library\s*\(\s*"([^"]+)"\s*\)\s*\{', content):
        target_name = m.group(1)
        start = m.end()
        # 花括号计数提取 body
        depth = 1
        i = start
        while i < len(content) and depth > 0:
            if content[i] == '{':
                depth += 1
            elif content[i] == '}':
                depth -= 1
            i += 1
        body = content[start:i - 1]

        # 提取 output_name
        output_name = target_name
        om = re.search(r'output_name\s*=\s*"([^"]+)"', body)
        if om:
            output_name = om.group(1)

        # 提取 sources
        sources = []
        sm = re.search(r'sources\s*=\s*\[([^\]]*)\]', body, re.DOTALL)
        if sm:
            sources_text = sm.group(1)
            sources = re.findall(r'"([^"]+)"', sources_text)

        targets.append({
            'name': target_name,
            'output_name': output_name,
            'sources': sources,
        })

    return targets


def find_impl_file(func_name, source_files, component_dir):
    """在源文件列表中查找包含函数定义的文件。

    优先级: .cpp/.c 实现文件 > .h 头文件
    排除测试目录。
    """
    candidates = []

    for src in source_files:
        src_path = Path(src)
        # 跳过测试目录
        parts = src_path.parts
        if any(p.lower() in EXCLUDE_DIRS for p in parts):
            continue

        # 优先选择 .cpp/.c 文件
        if src_path.suffix in IMPL_EXTENSIONS:
            full_path = component_dir / src
            if full_path.exists():
                candidates.append((0, str(full_path), src))  # 优先级最高
        elif src_path.suffix in HEADER_EXTENSIONS:
            full_path = component_dir / src
            if full_path.exists():
                candidates.append((1, str(full_path), src))  # 优先级次之

    if not candidates:
        return None, None

    # 按优先级排序后，grep 验证函数名
    candidates.sort(key=lambda x: x[0])
    for _, full_path, rel_path in candidates:
        try:
            content = Path(full_path).read_text(encoding='utf-8', errors='replace')
            # 检查函数定义（函数名后跟参数列表和花括号）
            if re.search(rf'\b{re.escape(func_name)}\s*\([^)]*\)\s*\{{', content):
                return str(full_path), rel_path
            # 降级检查：函数名出现在文件中
            if func_name in content:
                return str(full_path), rel_path
        except Exception:
            continue

    # 如果 grep 都没命中，返回优先级最高的候选
    return candidates[0][1], candidates[0][2]


def find_framework_decl(impl_file, component_dir):
    """尝试从实现文件所在目录向上查找 Framework 接口头文件。"""
    if not impl_file:
        return ''

    impl_path = Path(impl_file)
    # 查找 interfaces/ 目录
    for parent in impl_path.parents:
        if parent.name == 'src' and (parent.parent / 'include').is_dir():
            # frameworks/native/src → frameworks/native/include
            include_dir = parent.parent / 'include'
            h_files = list(include_dir.glob('*.h'))
            if h_files:
                return str(h_files[0])
        if parent.name == 'frameworks' and (parent / 'interfaces').is_dir():
            # 可能存在 interfaces/inner_api
            inner_api = parent / 'interfaces'
            for h in inner_api.rglob('*.h'):
                return str(h)

    return ''


def build_library_to_repo_map(databases_dir):
    """构建 library .so 名到 component repo 的映射。

    遍历 databases_dir 下的所有 BUILD.gn 文件，提取 ohos_shared_library 的 output_name。
    """
    db_path = Path(databases_dir)
    if not db_path.is_dir():
        return {}

    lib_map = {}  # output_name (不含 .so) → component_dir

    for build_gn in db_path.rglob('BUILD.gn'):
        targets = find_library_in_build_gn(build_gn)
        for t in targets:
            # output_name → lib{output_name}.so 或 {output_name}.so
            lib_name = t['output_name']
            # 存储映射，可能多个 repo 构建同名库（取第一个）
            if lib_name not in lib_map:
                # 解析相对于 databases_dir 的顶层仓库名
                try:
                    rel = build_gn.relative_to(db_path)
                    repo_name = rel.parts[0]  # 顶层目录即为仓库名
                except ValueError:
                    repo_name = build_gn.parent.name

                lib_map[lib_name] = {
                    'component_dir': build_gn.parent,
                    'repo_name': repo_name,
                    'build_gn': str(build_gn),
                    'sources': t['sources'],
                    'target_name': t['name'],
                }

    return lib_map


def map_c_api_records(records, lib_map, databases_dir):
    """为 C API 记录映射实现文件。"""
    mapped = 0
    unmapped = 0

    for rec in records:
        library = rec.get('library', '')
        func_name = extract_function_name(rec.get('api_declaration', ''))

        if not library or not func_name:
            unmapped += 1
            continue

        # 从 @library 提取库名（去掉 .so 后缀）
        lib_name = library.replace('.so', '').replace('.z.so', '')
        # 去掉 lib 前缀尝试匹配
        lib_name_no_prefix = lib_name.lstrip('lib')

        # 尝试多种匹配策略
        match = None
        for candidate in [lib_name, lib_name_no_prefix, f"lib{lib_name_no_prefix}"]:
            if candidate in lib_map:
                match = lib_map[candidate]
                break

        if not match:
            # 在全量 lib_map 中模糊搜索
            for key, val in lib_map.items():
                if lib_name in key or key in lib_name:
                    match = val
                    break

        if not match:
            unmapped += 1
            continue

        component_dir = match['component_dir']
        impl_repo_path = match['repo_name']

        # 从 sources 查找实现文件
        impl_full, impl_rel = find_impl_file(func_name, match['sources'], component_dir)

        if impl_full:
            rec['impl_repo_path'] = impl_repo_path
            rec['impl_file_path'] = impl_rel
            mapped += 1
        else:
            # 即使没找到具体实现文件，也填充 repo 路径
            rec['impl_repo_path'] = impl_repo_path
            unmapped += 1

    return mapped, unmapped


def main():
    parser = argparse.ArgumentParser(
        description='C API 实现文件映射脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--api_jsonl', required=True,
        help='api.jsonl 文件路径',
    )
    parser.add_argument(
        '--databases', required=True,
        help='DataBases 目录路径（包含 component repos）',
    )
    parser.add_argument(
        '-o', '--output', default='.',
        help='输出目录',
    )
    args = parser.parse_args()

    # 加载 C API 记录
    print(f"[Phase 2C] 加载 C API 记录: {args.api_jsonl}")
    c_records = load_api_records(args.api_jsonl)
    print(f"  C API 记录数: {len(c_records)}")

    if not c_records:
        print("  无 C API 记录，跳过。")
        return

    # 构建库名映射
    print(f"\n[Phase 2C] 扫描 DataBases 构建 library 映射: {args.databases}")
    lib_map = build_library_to_repo_map(args.databases)
    print(f"  发现 {len(lib_map)} 个 shared library 目标")

    # 映射
    print(f"\n[Phase 2C] 映射 C API 实现文件...")
    mapped, unmapped = map_c_api_records(c_records, lib_map, args.databases)
    total = mapped + unmapped
    coverage = mapped / total * 100 if total > 0 else 0
    print(f"  映射成功: {mapped}/{total} ({coverage:.1f}%)")
    print(f"  未映射: {unmapped}")

    # 输出结果
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 写 c_impl_map.json
    map_output = out_dir / 'c_impl_map.json'
    map_data = {
        'statistics': {
            'total_c_apis': total,
            'mapped': mapped,
            'unmapped': unmapped,
            'coverage_percent': round(coverage, 1),
        },
        'library_map_size': len(lib_map),
        'unmapped_apis': [
            {
                'api_declaration': r.get('api_declaration', ''),
                'library': r.get('library', ''),
                'impl_repo_path': r.get('impl_repo_path', ''),
            }
            for r in c_records
            if not r.get('impl_file_path')
        ],
    }
    with open(map_output, 'w', encoding='utf-8') as f:
        json.dump(map_data, f, ensure_ascii=False, indent=2)
    print(f"\n  映射详情: {map_output}")

    # 更新 api.jsonl（将映射结果写回）
    all_records = []
    with open(args.api_jsonl, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get('api_type') == 'c':
                # 查找映射结果
                for c_rec in c_records:
                    if (c_rec.get('api_declaration') == rec.get('api_declaration') and
                            c_rec.get('module_name') == rec.get('module_name')):
                        for field in ['impl_repo_path', 'impl_file_path', 'Framework_decl_file']:
                            if c_rec.get(field):
                                rec[field] = c_rec[field]
                        break
            all_records.append(rec)

    # 写回 api.jsonl
    with open(args.api_jsonl, 'w', encoding='utf-8') as f:
        for rec in all_records:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(f"  更新 api.jsonl: {args.api_jsonl}")


if __name__ == '__main__':
    main()
