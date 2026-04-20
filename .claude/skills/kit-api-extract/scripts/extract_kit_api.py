#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 HarmonyOS SDK 声明文件中提取所有方法级 API 信息。

支持两种 SDK:
  - interface_sdk-js: 扫描 .d.ts / .d.ets 声明文件
  - interface_sdk_c:  扫描 .h 头文件

用法:
    python3 extract_kit_api.py -js_decl_repo <js_sdk_dir> [-c_decl_repo <c_sdk_dir>] [-o output_dir] [--kit NAME]

    -js_decl_repo:  interface_sdk-js 目录路径
    -c_decl_repo:   interface_sdk_c 目录路径（可选）
    output_dir:     输出目录（默认: output）
    --kit NAME:     仅输出指定 kit 的 API（可选）

输出文件:
    不指定 --kit 时，按 kit 分目录输出:
      <output_dir>/<Kit_Name>/api.jsonl
      示例: output/Ability_Kit/api.jsonl

    指定 --kit 时，直接输出单个文件:
      <output_dir>/api.jsonl
      示例: output/api.jsonl

示例:
    # 仅提取 JS SDK
    python3 extract_kit_api.py -js_decl_repo /path/to/interface_sdk-js -o output

    # 仅提取 C SDK
    python3 extract_kit_api.py -c_decl_repo /path/to/interface_sdk_c -o output

    # 同时提取 JS + C SDK
    python3 extract_kit_api.py -js_decl_repo /path/to/interface_sdk-js -c_decl_repo /path/to/interface_sdk_c -o output

    # 仅输出 Ability Kit
    python3 extract_kit_api.py -js_decl_repo /path/to/interface_sdk-js -c_decl_repo /path/to/interface_sdk_c -o output --kit "Ability Kit"
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


# ============================================================
# Kit 名称规范化
# ============================================================

SPECIAL_KIT_NAMES = {
    'ArkUI': 'ArkUI',
    'ArkWeb': 'ArkWeb',
    'ArkData': 'ArkData',
    'ArkTS': 'ArkTS',
    'ArkGraphics2D': 'ArkGraphics 2D',
    'ArkGraphics3D': 'ArkGraphics 3D',
}


def normalize_kit_name(kit):
    """将代码中的 kit 名转换为显示名，如 AbilityKit → Ability Kit。"""
    if not kit:
        return ''
    # 去掉尾部标点
    kit = kit.rstrip('.,;:')
    # 已知全大写缩写 + Kit 的模式: IMEKit → IME Kit
    m = re.match(r'^([A-Z]{2,})(Kit)$', kit)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    if kit in SPECIAL_KIT_NAMES:
        return SPECIAL_KIT_NAMES[kit]
    # 处理 "XxxKit" 结尾：MindSporeLiteKit → Mind Spore Lite Kit
    if kit.endswith('Kit') and len(kit) > 3:
        prefix = kit[:-3]
        words = re.sub(r'([a-z])([A-Z])', r'\1 \2', prefix).split()
        return ' '.join(words) + ' Kit'
    # 一般 camelCase 分词
    words = re.sub(r'([a-z])([A-Z])', r'\1 \2', kit).split()
    # 标准化内部空格
    return ' '.join(words)


# ============================================================
# JSDoc / Doxygen 元数据提取
# ============================================================

def extract_tag_value(blocks, tag):
    """从注释块列表中提取标签值（取最后一个块的值）。"""
    for block in reversed(blocks):
        for line in block.split('\n'):
            m = re.match(rf'\s*\*\s*{re.escape(tag)}\s+(.+)', line)
            if m:
                return m.group(1).strip()
    return ''


def has_tag(blocks, tag):
    """检查注释块列表中是否包含某标签。"""
    for block in blocks:
        for line in block.split('\n'):
            if re.match(rf'\s*\*\s*{re.escape(tag)}\b', line):
                return True
    return False


def extract_throws(blocks):
    """从 JSDoc 块列表中提取 @throws 错误码列表。"""
    error_codes = []
    seen = set()
    for block in blocks:
        lines = block.split('\n')
        i = 0
        while i < len(lines):
            m = re.match(
                r'\s*\*\s*@throws\s*\{\s*\w+\s*\}\s*(\d+)\s*-\s*(.+)', lines[i]
            )
            if m:
                code = m.group(1)
                msg = m.group(2).strip()
                # 多行消息续行
                j = i + 1
                while j < len(lines):
                    nxt = lines[j].strip()
                    if nxt.startswith('* ') and not re.match(r'\*\s*@', nxt) and nxt != '*/':
                        msg += ' ' + nxt[2:].strip()
                        j += 1
                    else:
                        break
                if code not in seen:
                    seen.add(code)
                    error_codes.append({"code": code, "message": msg})
                i = j
            else:
                i += 1
    return error_codes


def extract_jsdoc_metadata(blocks):
    """从合并的 JSDoc 块中提取元数据字典。"""
    since_raw = extract_tag_value(blocks, '@since')
    api_version = ''
    if since_raw:
        m = re.match(r'(\d+)', since_raw)
        if m:
            api_version = m.group(1)
    return {
        'syscap': extract_tag_value(blocks, '@syscap'),
        'permission': extract_tag_value(blocks, '@permission'),
        'api_version': api_version,
        'is_system_api': has_tag(blocks, '@systemapi'),
        'error_codes': extract_throws(blocks),
    }


# ============================================================
# 声明文本提取
# ============================================================

def extract_declaration_text(text):
    """从注释块后的文本中提取声明（到 ; 或 } 或下一个 /** 为止）。"""
    text = text.lstrip()
    if not text:
        return ''
    brace = 0
    in_str = False
    sch = None
    for i, ch in enumerate(text):
        if ch in '"\'`' and (i == 0 or text[i - 1] != '\\'):
            if not in_str:
                in_str = True
                sch = ch
            elif ch == sch:
                in_str = False
        elif not in_str:
            if ch == '{':
                brace += 1
            elif ch == '}':
                brace -= 1
                if brace < 0:
                    return text[:i].strip()
            elif ch == ';' and brace == 0:
                return text[:i].strip()
            elif text[i:i + 3] == '/**':
                return text[:i].strip()
    # 没找到结束符，取到第一个空行
    dnl = text.find('\n\n')
    if dnl > 0:
        return text[:dnl].strip()
    return text.strip()


# ============================================================
# 声明分类
# ============================================================

# 容器类型声明（内部可能有方法，但自身不是方法级 API）
CONTAINER_TYPES = {'class', 'interface', 'enum', 'namespace', 'struct'}
# 方法级声明（需要提取）
METHOD_TYPES = {'function', 'method', 'constructor', 'getter', 'setter'}


def classify_declaration(decl):
    """
    分类声明类型。
    返回: 'function' | 'method' | 'constructor' | 'getter' | 'setter'
          | 'class' | 'interface' | 'enum' | 'namespace' | 'struct'
          | 'type' | 'property' | 'export' | 'other'
    """
    d = decl.strip()
    d_one_line = ' '.join(d.split())

    # --- 容器类型 ---
    if re.match(r'^(?:export\s+)?(?:declare\s+)?enum\s+', d_one_line):
        return 'enum'
    if re.match(r'^(?:export\s+)?(?:declare\s+)?namespace\s+', d_one_line):
        return 'namespace'
    if re.match(r'^(?:export\s+)?(?:declare\s+)?(?:abstract\s+)?class\s+', d_one_line):
        return 'class'
    if re.match(r'^(?:export\s+)?(?:declare\s+)?interface\s+', d_one_line):
        return 'interface'
    if re.match(r'^(?:@\w+\s*\n?\s*)*(?:export\s+)?(?:declare\s+)?struct\s+', d):
        return 'struct'

    # --- type 别名 ---
    if re.match(r'^(?:export\s+)?type\s+\w+\s*=', d_one_line):
        return 'type'

    # --- import/export ---
    if re.match(r'^export\s+(default\s+)', d_one_line):
        return 'export'
    if re.match(r'^export\s*\{', d_one_line):
        return 'export'
    if re.match(r'^import\s+', d_one_line):
        return 'export'

    # --- 方法级声明 ---

    # function 声明
    if re.match(r'^(?:@\w+\s*\n?\s*)*(?:export\s+)?(?:declare\s+)?function\s+\w+', d):
        return 'function'

    # constructor
    if re.match(r'^constructor\s*\(', d_one_line):
        return 'constructor'

    # getter / setter
    if re.match(r'^(?:static\s+)?get\s+\w+\s*\(', d_one_line):
        return 'getter'
    if re.match(r'^(?:static\s+)?set\s+\w+\s*\(', d_one_line):
        return 'setter'

    # 去装饰器后检测通用方法签名
    d_clean = d_one_line
    while d_clean.startswith('@'):
        m = re.match(r'@\w+\s*', d_clean)
        if m:
            d_clean = d_clean[m.end():].lstrip()
        else:
            break

    m = re.match(
        r'^(?:static\s+)?(?:readonly\s+)?(?:abstract\s+)?(\w+)', d_clean
    )
    if m:
        name = m.group(1)
        rest = d_clean[m.end():]

        # 跳过关键字
        if name in ('const', 'let', 'var', 'declare', 'export', 'import',
                     'type', 'enum', 'class', 'interface', 'namespace',
                     'function', 'new', 'delete', 'return'):
            return 'other'

        # 跳过泛型参数
        if rest.startswith('<'):
            depth = 0
            for ci, c in enumerate(rest):
                if c == '<':
                    depth += 1
                elif c == '>':
                    depth -= 1
                    if depth == 0:
                        rest = rest[ci + 1:].lstrip()
                        break

        # 可选标记
        if rest.startswith('?'):
            rest = rest[1:].lstrip()

        # 有 ( → 方法
        if rest.startswith('('):
            return 'method'

        # 没括号 → 属性
        return 'property'

    return 'other'


# ============================================================
# 签名构建
# ============================================================

def build_clean_signature(decl, decl_type):
    """从声明文本构建干净的 API 签名（保留 function 前缀，去掉多余修饰符）。"""
    d = ' '.join(decl.split())

    if decl_type == 'function':
        # 保留 function 前缀，去掉 export / declare / 装饰器
        d = re.sub(r'^(?:@\w+\s*)*(?:export\s+)?(?:declare\s+)?(function\s+)', r'\1', d)
    elif decl_type == 'constructor':
        pass  # constructor(params) 直接保留
    elif decl_type in ('getter', 'setter'):
        # get name(): type 保留
        pass
    elif decl_type == 'method':
        # 去装饰器
        while d.startswith('@'):
            m = re.match(r'@\w+\s*', d)
            if m:
                d = d[m.end():].lstrip()
            else:
                break
        # 去掉 abstract
        d = re.sub(r'^abstract\s+', '', d)

    return d.rstrip(';').strip()


# ============================================================
# JS/TS 文件解析 (.d.ts / .d.ets)
# ============================================================

def extract_file_kit(content):
    """从文件开头的 JSDoc 中提取 @kit 标签值。"""
    for line in content.split('\n')[:40]:
        m = re.match(r'\s*\*\s*@kit\s+(\S+)', line)
        if m:
            return m.group(1)
    return ''


def parse_js_file(file_path, sdk_api_dir=None):
    """解析单个 .d.ts / .d.ets 文件，返回方法级 API 记录列表。"""
    try:
        content = file_path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return []

    if not content.strip():
        return []

    file_kit = extract_file_kit(content)
    # 模块名 = 文件名去掉 .d.ts / .d.ets 后缀
    module_name = file_path.stem
    if module_name.endswith('.d'):
        module_name = module_name[:-2]

    # declaration_file: 保持 api/ 前缀的相对路径
    if sdk_api_dir:
        try:
            decl_file = f"api/{file_path.relative_to(sdk_api_dir)}"
        except ValueError:
            decl_file = file_path.name
    else:
        decl_file = f"api/{file_path.name}"

    # 查找所有 JSDoc 块
    jsdoc_re = re.compile(r'/\*\*[\s\S]*?\*/', re.MULTILINE)
    matches = list(jsdoc_re.finditer(content))
    if not matches:
        return []

    records = []
    i = 0

    while i < len(matches):
        # 收集连续的 JSDoc 块
        blocks = [matches[i]]
        j = i + 1
        while j < len(matches):
            gap = content[matches[j - 1].end():matches[j].start()]
            if gap.strip() == '':
                blocks.append(matches[j])
                j += 1
            else:
                break

        # 提取声明
        after_text = content[blocks[-1].end():]
        decl = extract_declaration_text(after_text)

        if decl:
            decl_type = classify_declaration(decl)

            if decl_type in METHOD_TYPES:
                jsdoc_texts = [b.group() for b in blocks]

                # kit: 优先方法级 @kit，其次文件级
                method_kit = extract_tag_value(jsdoc_texts, '@kit')
                kit = normalize_kit_name(method_kit or file_kit)

                sig = build_clean_signature(decl, decl_type)

                records.append({
                    "api_declaration": sig,
                    "js_doc": '\n'.join(jsdoc_texts),
                    "module_name": module_name,
                    "declaration_file": decl_file,
                    "api_type": "js",
                    "_kit": kit,
                })

        i = j

    return records


# ============================================================
# C 头文件解析 (.h)
# ============================================================

def extract_c_file_metadata(content):
    """从 C 头文件中提取文件级元数据 (@kit, @syscap, @library)。"""
    kit = ''
    syscap = ''
    library = ''
    in_file_block = False

    for line in content.split('\n')[:100]:
        stripped = line.strip()
        if '/**' in stripped:
            in_file_block = True
        if in_file_block:
            m = re.match(r'\s*\*\s*@kit\s+(\S+)', line)
            if m:
                kit = m.group(1)
            m = re.match(r'\s*\*\s*@syscap\s+(.+)', line)
            if m:
                val = m.group(1).strip()
                if not val.startswith('SystemCapability'):
                    val = f"SystemCapability.{val}"
                syscap = val
            m = re.match(r'\s*\*\s*@library\s+(\S+)', line)
            if m:
                library = m.group(1)
            # @file 标记表示这是文件级注释块
            m = re.match(r'\s*\*\s*@file\b', line)
            if m:
                in_file_block = True
        if '*/' in stripped and in_file_block:
            in_file_block = False

    return kit, syscap, library


def parse_c_function(line):
    """解析 C 函数声明行，返回签名或 None。"""
    line = ' '.join(line.split()).strip().rstrip(';').strip()
    if not line or '(' not in line:
        return None

    # 跳过非函数声明
    if line.startswith(('#', 'typedef', 'enum', 'struct', 'union', 'extern')):
        return None

    # 匹配函数声明: 返回类型 函数名(参数)，支持 OH_ 和 OHOS_ 前缀
    m = re.match(r'^([\w\s\*]+?)\b((?:OH|OHOS)_\w+)\s*\(([^;]*)\)', line)
    if m:
        ret = m.group(1).strip()
        name = m.group(2)
        params = m.group(3).strip()
        if ret:
            return f"{ret} {name}({params})"

    return None


def parse_c_file(file_path, c_sdk_root=None):
    """解析单个 .h 头文件，返回函数 API 记录列表。"""
    try:
        content = file_path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return []

    if not content.strip():
        return []

    file_kit, file_syscap, file_library = extract_c_file_metadata(content)

    # module_name: 从文件路径推导，如 CryptoArchitectureKit/crypto_digest.h → CryptoArchitectureKit.crypto_digest
    if c_sdk_root:
        try:
            rel = file_path.relative_to(c_sdk_root)
            # 取路径的前两级：CryptoArchitectureKit/crypto_digest.h → CryptoArchitectureKit.crypto_digest
            parts = rel.with_suffix('').parts
            if len(parts) >= 2:
                module_name = f"{parts[0]}.{parts[-1]}"
            else:
                module_name = parts[0]
        except ValueError:
            module_name = file_path.stem
    else:
        module_name = file_path.stem

    # declaration_file: 相对于 SDK 根目录的路径
    if c_sdk_root:
        try:
            declaration_file = str(file_path.relative_to(c_sdk_root))
        except ValueError:
            declaration_file = file_path.name
    else:
        declaration_file = file_path.name

    records = []

    # 找所有 Doxygen 注释块，然后检查后面的函数声明
    doxygen_re = re.compile(r'/\*\*[\s\S]*?\*/', re.MULTILINE)
    matches = list(doxygen_re.finditer(content))

    for match in matches:
        comment = match.group()
        after = content[match.end():].lstrip()

        # 取第一行作为声明
        lines = after.split('\n')
        first_line = lines[0].strip()

        # 如果是多行函数声明，合并到右括号
        full_decl = first_line
        if '(' in full_decl and ')' not in full_decl:
            for ln in lines[1:]:
                full_decl += ' ' + ln.strip()
                if ')' in ln:
                    break

        sig = parse_c_function(full_decl)
        if not sig:
            continue

        # 从 Doxygen 注释提取元数据
        since = ''
        for ln in comment.split('\n'):
            m = re.match(r'\s*\*\s*@since\s+(\d+)', ln)
            if m:
                since = m.group(1)

        permission = ''
        for ln in comment.split('\n'):
            m = re.match(r'\s*\*\s*@permission\s+(.+)', ln)
            if m:
                permission = m.group(1).strip()

        kit = normalize_kit_name(file_kit)

        records.append({
            "api_declaration": sig,
            "js_doc": comment,
            "module_name": module_name,
            "declaration_file": declaration_file,
            "api_type": "c",
            "library": file_library,
            "_kit": kit,
        })

    return records


# ============================================================
# SDK 类型检测与文件扫描
# ============================================================

def detect_sdk_type(sdk_dir):
    """自动检测 SDK 类型。"""
    p = Path(sdk_dir)
    has_api = (p / 'api').is_dir()
    has_kits = (p / 'kits').is_dir()

    if has_api or has_kits:
        return 'js'

    # 直接在根目录查找
    dts = list(p.glob('*.d.ts')) + list(p.glob('*.d.ets'))
    h_files = list(p.glob('*.h'))

    if dts and not h_files:
        return 'js'
    if h_files and not dts:
        return 'c'
    if dts and h_files:
        return 'both'
    if not dts and not h_files:
        # 递归查找
        dts_r = list(p.rglob('*.d.ts'))[:1] + list(p.rglob('*.d.ets'))[:1]
        h_r = list(p.rglob('*.h'))[:1]
        if dts_r:
            return 'js'
        if h_r:
            return 'c'

    return None


def scan_js_sdk(sdk_dir):
    """扫描 JS SDK，返回所有 .d.ts / .d.ets 文件路径。"""
    p = Path(sdk_dir)
    files = []

    # api/ 子目录
    api_dir = p / 'api'
    if api_dir.is_dir():
        files.extend(api_dir.rglob('*.d.ts'))
        files.extend(api_dir.rglob('*.d.ets'))

    # arkts/ 子目录
    arkts_dir = p / 'arkts'
    if arkts_dir.is_dir():
        files.extend(arkts_dir.rglob('*.d.ts'))
        files.extend(arkts_dir.rglob('*.d.ets'))

    # 如果没有子目录结构，直接扫描根目录
    if not files:
        files.extend(p.rglob('*.d.ts'))
        files.extend(p.rglob('*.d.ets'))

    # 去重
    seen = set()
    unique = []
    for f in files:
        if f not in seen:
            seen.add(f)
            unique.append(f)
    return sorted(unique)


def scan_c_sdk(sdk_dir):
    """扫描 C SDK，返回所有 .h 文件路径。"""
    return sorted(Path(sdk_dir).rglob('*.h'))


# ============================================================
# 输出
# ============================================================

def write_output(kit_records, output_dir, total, kit_filter=None):
    """按 kit 写入 JSONL 文件。

    指定 kit_filter 时: <output_dir>/api.jsonl (单个文件)
    不指定时:          <output_dir>/<Kit_Name>/api.jsonl (每个 kit 一个子目录)
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for kit_name in sorted(kit_records.keys()):
        if kit_filter and kit_name != kit_filter:
            continue
        records = kit_records[kit_name]
        if kit_filter:
            # 指定 kit: 直接输出到 <output_dir>/api.jsonl
            of = out / "api.jsonl"
        else:
            # 全量: 每个 kit 一个子目录 <output_dir>/<Kit_Name>/api.jsonl
            safe = kit_name.replace(' ', '_') if kit_name else 'Unknown'
            kit_dir = out / safe
            kit_dir.mkdir(parents=True, exist_ok=True)
            of = kit_dir / "api.jsonl"
        with open(of, 'w', encoding='utf-8') as f:
            for r in records:
                # 输出时去掉内部 _kit 字段
                rec = {k: v for k, v in r.items() if k != '_kit'}
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        print(f"  {kit_name or '(no kit)'}: {len(records)} 条 API -> {of.relative_to(out)}")

    print(f"\n总计: {total} 条 API, {len(kit_records)} 个 kit")

    # 统计
    all_recs = [r for rs in kit_records.values() for r in rs]
    no_paren = sum(1 for r in all_recs if '(' not in r['api_declaration'])
    print(f"无效签名 (无括号): {no_paren}")


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='从 HarmonyOS SDK 声明文件中提取所有方法级 API 信息',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''示例:
  # 仅提取 JS SDK
  python3 extract_kit_api.py -js_decl_repo /path/to/interface_sdk-js -o output

  # 仅提取 C SDK
  python3 extract_kit_api.py -c_decl_repo /path/to/interface_sdk_c -o output

  # 同时提取 JS + C SDK
  python3 extract_kit_api.py -js_decl_repo /path/to/interface_sdk-js -c_decl_repo /path/to/interface_sdk_c -o output

  # 仅输出指定 kit
  python3 extract_kit_api.py -js_decl_repo /path/to/interface_sdk-js -o output --kit "Ability Kit"
  python3 extract_kit_api.py -js_decl_repo /path/to/interface_sdk-js -c_decl_repo /path/to/interface_sdk_c -o output --kit "Ability Kit"
        ''',
    )
    parser.add_argument(
        '-js', '--js_decl_repo',
        default=None,
        help='JS/TS SDK 目录路径 (interface_sdk-js)',
    )
    parser.add_argument(
        '-c', '--c_decl_repo',
        default=None,
        help='C SDK 目录路径 (interface_sdk_c)',
    )
    parser.add_argument(
        '-o', '--output',
        default='output',
        help='输出目录 (默认: output)',
    )
    parser.add_argument(
        '--kit',
        default=None,
        help='仅输出指定 kit 的 API (如 "Ability Kit")',
    )
    args = parser.parse_args()

    if not args.js_decl_repo and not args.c_decl_repo:
        parser.error('至少需要指定 -js_decl_repo 或 -c_decl_repo 中的一个')

    kit_records = defaultdict(list)
    total = 0

    if args.js_decl_repo:
        js_path = Path(args.js_decl_repo)
        if not js_path.is_dir():
            print(f"错误: JS SDK 目录不存在: {args.js_decl_repo}", file=sys.stderr)
            sys.exit(1)
        files = scan_js_sdk(js_path)
        api_dir = js_path / 'api' if (js_path / 'api').is_dir() else js_path
        print(f"[JS SDK] {js_path}")
        print(f"发现 {len(files)} 个声明文件 (.d.ts / .d.ets)\n")
        for fp in files:
            recs = parse_js_file(fp, sdk_api_dir=api_dir)
            for r in recs:
                kit_records[r['_kit']].append(r)
                total += 1

    if args.c_decl_repo:
        c_path = Path(args.c_decl_repo)
        if not c_path.is_dir():
            print(f"错误: C SDK 目录不存在: {args.c_decl_repo}", file=sys.stderr)
            sys.exit(1)
        files = scan_c_sdk(c_path)
        print(f"[C SDK] {c_path}")
        print(f"发现 {len(files)} 个头文件 (.h)\n")
        for fp in files:
            recs = parse_c_file(fp, c_sdk_root=c_path)
            for r in recs:
                kit_records[r['_kit']].append(r)
                total += 1

    write_output(kit_records, args.output, total, kit_filter=args.kit)


if __name__ == '__main__':
    main()
