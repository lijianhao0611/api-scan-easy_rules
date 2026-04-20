#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 HarmonyOS/OpenHarmony 部件仓中提取结构关系映射表。

通过解析 bundle.json、BUILD.gn 和 C++ 源文件中的 nm_modname，
为指定 Kit 建立组件→模块→文件的确定性映射关系。

用法:
    python3 extract_component_map.py \
      --kit "Media Library Kit" \
      --databases /path/to/DataBases \
      --csv /path/to/kit_compont.csv \
      -o output_dir

输出:
    <output_dir>/component_map.json — 结构化映射表
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path


# ============================================================
# Kit 名称匹配
# ============================================================

def load_kit_components(csv_path):
    """从 kit_compont.csv 加载 Kit → 部件目录列表的映射。"""
    kit_map = {}
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                kit = row.get('kit', '').strip()
                comp = row.get('component', '').strip()
                if kit and comp:
                    kit_lower = kit.lower()
                    if kit_lower not in kit_map:
                        kit_map[kit_lower] = []
                    kit_map[kit_lower].append(comp)
    except Exception as e:
        print(f"[Error] Failed to read CSV: {e}", file=sys.stderr)
        sys.exit(1)
    return kit_map


def resolve_kit_name(input_name, kit_map):
    """将用户输入的 Kit 名称匹配到 CSV 中的 Kit 名称（case-insensitive）。

    返回 (matched_display_name, component_dirs) 或 (None, [])。
    """
    input_lower = input_name.lower().strip()
    # 直接匹配
    if input_lower in kit_map:
        # 找到原始显示名
        for kit_key in kit_map:
            if kit_key == input_lower:
                return kit_key, kit_map[kit_key]
    # 去掉 "Kit" 后缀再试
    input_no_kit = re.sub(r'\s*kit\s*$', '', input_lower).strip()
    for kit_key in kit_map:
        kit_no_kit = re.sub(r'\s*kit\s*$', '', kit_key).strip()
        if input_no_kit == kit_no_kit:
            return kit_key, kit_map[kit_key]
    # 子串匹配
    for kit_key in kit_map:
        if input_lower in kit_key or kit_key in input_lower:
            return kit_key, kit_map[kit_key]
    return None, []


# ============================================================
# bundle.json 解析
# ============================================================

def parse_bundle_json(bundle_path):
    """解析 bundle.json，提取组件元信息。"""
    try:
        with open(bundle_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"  [Warning] Failed to parse {bundle_path}: {e}", file=sys.stderr)
        return None

    result = {
        'bundle_file': str(bundle_path),
        'component': {},
        'segment': {},
        'build': {},
        'deps': {},
        'inner_kits': [],
        'syscap': [],
    }

    # 组件身份
    comp = data.get('component', {})
    result['component'] = {
        'name': comp.get('name', ''),
        'subsystem': comp.get('subsystem', ''),
    }

    # 段路径
    seg = data.get('segment', {})
    result['segment'] = {
        'destPath': seg.get('destPath', ''),
    }

    # SysCap
    result['syscap'] = comp.get('syscap', [])

    # 依赖
    deps = data.get('deps', {})
    result['deps'] = {
        'components': deps.get('components', []),
        'third_party': deps.get('third_party', []),
    }

    # 构建目标
    build = data.get('build', {})
    group_type = build.get('group_type', {})
    result['build'] = {
        'fwk_group': group_type.get('fwk_group', []) if isinstance(group_type, dict) else [],
        'service_group': group_type.get('service_group', []) if isinstance(group_type, dict) else [],
        'sub_component': build.get('sub_component', []),
    }

    # Inner kits
    inner_kits = build.get('inner_kits', build.get('inner_api', []))
    for ik in inner_kits:
        entry = {
            'name': ik.get('name', ''),
            'type': ik.get('type', ''),
        }
        header = ik.get('header', {})
        if header:
            entry['header_base'] = header.get('header_base', '')
            entry['header_files'] = header.get('header_files', [])
        result['inner_kits'].append(entry)

    return result


# ============================================================
# BUILD.gn 解析（最小可行方案：仅处理静态赋值）
# ============================================================

def parse_build_gn(build_gn_path, base_dir):
    """解析 BUILD.gn 文件，提取 target 信息。

    仅处理直接赋值的静态 sources 列表，跳过变量引用和条件分支。
    """
    try:
        content = build_gn_path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return []

    targets = []
    lines = content.split('\n')

    # 匹配 target 定义: ohos_shared_library("name") {
    target_re = re.compile(
        r'(ohos_shared_library|ohos_static_library|js_declaration)\s*\(\s*["\']([^"\']+)["\']\s*\)\s*\{'
    )

    i = 0
    while i < len(lines):
        m = target_re.search(lines[i])
        if not m:
            i += 1
            continue

        target_type = m.group(1)
        target_name = m.group(2)
        target_info = {
            'type': target_type,
            'name': target_name,
            'build_gn_file': str(build_gn_path.relative_to(base_dir)) if base_dir else str(build_gn_path),
            'sources': [],
            'relative_install_dir': '',
            'deps': [],
        }

        # 收集 target body（到匹配的 } 为止）
        brace_count = 0
        started = False
        j = i
        body_lines = []
        while j < len(lines):
            line = lines[j]
            if '{' in line:
                brace_count += line.count('{')
                started = True
            if '}' in line:
                brace_count -= line.count('}')
            body_lines.append(line)
            if started and brace_count <= 0:
                break
            j += 1

        body_text = '\n'.join(body_lines)

        # 提取 sources（仅直接赋值的字符串列表）
        src_match = re.search(r'sources\s*=\s*\[([^\]]*)\]', body_text, re.DOTALL)
        if src_match:
            raw = src_match.group(1)
            files = re.findall(r'["\']([^"\']+)["\']', raw)
            target_info['sources'] = files

        # 提取 relative_install_dir
        dir_match = re.search(r'relative_install_dir\s*=\s*["\']([^"\']+)["\']', body_text)
        if dir_match:
            target_info['relative_install_dir'] = dir_match.group(1)

        # 提取 deps（仅直接列表）
        deps_match = re.search(r'deps\s*=\s*\[([^\]]*)\]', body_text, re.DOTALL)
        if deps_match:
            raw = deps_match.group(1)
            deps = re.findall(r'["\':]([^"\':\s]+)["\':]?\s*', raw)
            target_info['deps'] = [d.strip() for d in deps if d.strip()]

        targets.append(target_info)
        i = j + 1

    return targets


# ============================================================
# nm_modname 扫描
# ============================================================

def scan_nm_modname(component_dir):
    """扫描 C++ 源文件中的 nm_modname 声明，建立模块名→入口文件映射。"""
    results = []
    nm_re = re.compile(r'\.nm_modname\s*=\s*"([^"]+)"')
    reg_func_re = re.compile(r'\.nm_register_func\s*=\s*(\w+)')

    component_path = Path(component_dir)
    for cpp_file in component_path.rglob('*.cpp'):
        try:
            content = cpp_file.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue

        for m in nm_re.finditer(content):
            modname = m.group(1)
            # 查找对应的 nm_register_func
            reg_func = ''
            reg_m = reg_func_re.search(content)
            if reg_m:
                reg_func = reg_m.group(1)

            # 从 nm_modname 推导 @ohos 模块名
            # "X.Y" → "@ohos.X.Y"
            ohos_name = f"@ohos.{modname}"

            results.append({
                'nm_modname': modname,
                'ohos_module': ohos_name,
                'entry_file': str(cpp_file),
                'register_func': reg_func,
            })

    # 也扫描 .c 文件
    for c_file in component_path.rglob('*.c'):
        try:
            content = c_file.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue

        for m in nm_re.finditer(content):
            modname = m.group(1)
            reg_func = ''
            reg_m = reg_func_re.search(content)
            if reg_m:
                reg_func = reg_m.group(1)

            ohos_name = f"@ohos.{modname}"

            results.append({
                'nm_modname': modname,
                'ohos_module': ohos_name,
                'entry_file': str(c_file),
                'register_func': reg_func,
            })

    return results


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='从部件仓中提取结构关系映射表',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''示例:
  python3 extract_component_map.py \\
    --kit "Media Library Kit" \\
    --databases /path/to/DataBases \\
    --csv /path/to/kit_compont.csv \\
    -o output
        ''',
    )
    parser.add_argument('--kit', required=True, help='Kit 名称（如 "Media Library Kit"、"Ability Kit"）')
    parser.add_argument('--databases', required=True, help='DataBases 目录路径')
    parser.add_argument('--csv', required=True, help='kit_compont.csv 文件路径')
    parser.add_argument('-o', '--output', default='output', help='输出目录（默认: output）')
    args = parser.parse_args()

    databases = Path(args.databases)
    if not databases.is_dir():
        print(f"[Error] DataBases directory not found: {args.databases}", file=sys.stderr)
        sys.exit(1)

    # Step 1: 加载 CSV 映射
    print(f"[Step 1] Loading kit-component mapping from {args.csv}")
    kit_map = load_kit_components(args.csv)

    # Step 2: 匹配 Kit 名称
    print(f"[Step 2] Resolving kit name: {args.kit}")
    matched_kit, component_dirs = resolve_kit_name(args.kit, kit_map)
    if not matched_kit:
        print(f"[Error] Kit '{args.kit}' not found in CSV. Available kits:", file=sys.stderr)
        for k in sorted(set(kit_map.keys())):
            print(f"  - {k}", file=sys.stderr)
        sys.exit(1)
    print(f"  Matched: '{matched_kit}' -> {component_dirs}")

    # Step 3: 扫描每个部件仓
    print(f"[Step 3] Scanning {len(component_dirs)} component directories")
    components = []

    for comp_dir_name in component_dirs:
        comp_path = databases / comp_dir_name
        if not comp_path.is_dir():
            print(f"  [Warning] Component directory not found: {comp_dir_name}", file=sys.stderr)
            continue

        print(f"  Scanning: {comp_dir_name}")

        # 3a. 解析 bundle.json
        bundle_path = comp_path / 'bundle.json'
        bundle_info = None
        if bundle_path.exists():
            bundle_info = parse_bundle_json(bundle_path)
            if bundle_info:
                print(f"    bundle.json: subsystem={bundle_info['component'].get('subsystem', '')}, "
                      f"syscap={len(bundle_info['syscap'])}, "
                      f"fwk_group={len(bundle_info['build']['fwk_group'])}, "
                      f"inner_kits={len(bundle_info['inner_kits'])}")

        # 3b. 解析 BUILD.gn 文件
        build_targets = []
        for gn_file in comp_path.rglob('BUILD.gn'):
            targets = parse_build_gn(gn_file, databases)
            build_targets.extend(targets)
        if build_targets:
            print(f"    BUILD.gn: {len(build_targets)} targets found")
            for t in build_targets:
                print(f"      {t['type']}(\"{t['name']}\") sources={len(t['sources'])}")

        # 3c. 扫描 nm_modname
        nm_entries = scan_nm_modname(comp_path)
        if nm_entries:
            print(f"    nm_modname: {len(nm_entries)} entries found")
            for ne in nm_entries:
                print(f"      \"{ne['nm_modname']}\" -> {Path(ne['entry_file']).name}")

        components.append({
            'component_dir': comp_dir_name,
            'component_path': str(comp_path),
            'bundle': bundle_info,
            'build_targets': build_targets,
            'nm_modname_entries': nm_entries,
        })

    # Step 4: 生成匹配汇总
    print(f"\n[Step 4] Building module mapping")
    module_map = {}
    unmatched = []

    for comp in components:
        for nm in comp['nm_modname_entries']:
            ohos_module = nm['ohos_module']
            entry = {
                'module_name': ohos_module,
                'nm_modname': nm['nm_modname'],
                'entry_file': nm['entry_file'],
                'register_func': nm['register_func'],
                'component_dir': comp['component_dir'],
                'related_targets': [],
            }
            # 关联 BUILD.gn target（通过 sources 匹配入口文件）
            entry_basename = Path(nm['entry_file']).name
            for t in comp['build_targets']:
                for src in t['sources']:
                    src_basename = Path(src).name
                    if src_basename == entry_basename:
                        entry['related_targets'].append({
                            'target_name': t['name'],
                            'target_type': t['type'],
                            'build_gn_file': t['build_gn_file'],
                            'sources': t['sources'],
                            'relative_install_dir': t.get('relative_install_dir', ''),
                        })
                        break

            module_map[ohos_module] = entry

    # 收集 unmatched（没有匹配到 @ohos.X.Y 命名的 nm_modname）
    for comp in components:
        for nm in comp['nm_modname_entries']:
            ohos_module = nm['ohos_module']
            # 检查这个模块名是否是标准的 @ohos.X.Y 格式
            # 标准格式：@ohos.xxx.yyy（至少两段）
            parts = nm['nm_modname'].split('.')
            if len(parts) < 1:
                unmatched.append(nm)

    # Step 5: 输出
    output = {
        'kit_name': matched_kit,
        'kit_input': args.kit,
        'component_dirs': component_dirs,
        'components': components,
        'module_map': module_map,
        'statistics': {
            'total_components': len(components),
            'total_build_targets': sum(len(c['build_targets']) for c in components),
            'total_nm_modname_entries': sum(len(c['nm_modname_entries']) for c in components),
            'mapped_modules': len(module_map),
        },
    }

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / 'component_map.json'
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[Done] Output: {out_file}")
    print(f"  Components: {output['statistics']['total_components']}")
    print(f"  BUILD.gn targets: {output['statistics']['total_build_targets']}")
    print(f"  nm_modname entries: {output['statistics']['total_nm_modname_entries']}")
    print(f"  Mapped @ohos modules: {output['statistics']['mapped_modules']}")


if __name__ == '__main__':
    main()
