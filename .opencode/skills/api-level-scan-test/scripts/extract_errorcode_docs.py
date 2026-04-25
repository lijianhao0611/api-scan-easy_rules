#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 HarmonyOS 文档仓库中提取指定 Kit 的错误码文档。

用法:
    python3 extract_errorcode_docs.py <docs_path> <kit_name> <output_path>

    docs_path:   文档仓路径 (包含 zh-cn 目录)
    kit_name:    Kit 名称，如 "Ability Kit"、"Network Kit"
    output_path: 输出目录

示例:
    python3 extract_errorcode_docs.py \\
        /Users/spongbob/for_guance/api_dfx_2.0/data/docs \\
        "Ability Kit" \\
        output
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

# 根索引文件中的 kit 链接格式: - [Ability Kit API参考](apis-ability-kit/Readme-CN.md)
KIT_LINK_RE = re.compile(r"^-\s+\[(.+?)\s+API参考\]\((.+?)/Readme-CN\.md\)$")

# 错误码章节标题: - 错误码<!--xxx-->
ERRCODE_SECTION_RE = re.compile(r"^\s*-\s+错误码<!--.*?-->")

# 错误码文件链接: - [xxx](errorcode-xxx.md) 或子目录下 [xxx](arkui-ts/errorcode-xxx.md)
ERRCODE_LINK_RE = re.compile(r"^\s+-\s+\[.+?\]\((.+?\.md)\)$")

# 新的顶级章节: 行首不带空格的 "- xxx"
TOP_LEVEL_RE = re.compile(r"^-\s+\S")


def resolve_kit_dir(kit_name: str, ref_dir: Path) -> str:
    """从根索引 Readme-CN.md 中查找 Kit 对应的目录名。"""
    readme_path = ref_dir / "Readme-CN.md"
    if not readme_path.exists():
        print(f"错误: 找不到根索引文件 {readme_path}", file=sys.stderr)
        sys.exit(1)

    content = readme_path.read_text(encoding="utf-8")
    for line in content.splitlines():
        m = KIT_LINK_RE.match(line.strip())
        if m and m.group(1).strip() == kit_name.strip():
            return m.group(2)

    print(f"错误: 在根索引中未找到 Kit '{kit_name}'", file=sys.stderr)
    sys.exit(1)


def parse_errorcode_files(readme_path: Path) -> list[str]:
    """解析 Readme-CN.md，提取错误码章节中的文件名，跳过 Del 块。"""
    if not readme_path.exists():
        print(f"错误: 找不到 Kit Readme 文件 {readme_path}", file=sys.stderr)
        sys.exit(1)

    content = readme_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    in_errcode_section = False
    in_del = False
    errorcode_files = []

    for line in lines:
        # 进入错误码章节
        if not in_errcode_section:
            if ERRCODE_SECTION_RE.match(line):
                in_errcode_section = True
            continue

        # 在错误码章节内，检测是否遇到新的顶级章节（结束）
        if TOP_LEVEL_RE.match(line) and not ERRCODE_SECTION_RE.match(line):
            break

        # 跟踪 Del 标记
        if "<!--Del-->" in line:
            in_del = True
            continue
        if "<!--DelEnd-->" in line:
            in_del = False
            continue

        # 跳过 Del 块中的内容
        if in_del:
            continue

        # 提取文件链接
        m = ERRCODE_LINK_RE.match(line)
        if m:
            errorcode_files.append(m.group(1))

    return errorcode_files


def main():
    parser = argparse.ArgumentParser(
        description="从 HarmonyOS 文档仓库提取指定 Kit 的错误码文档"
    )
    parser.add_argument("docs_path", help="文档仓路径")
    parser.add_argument("kit_name", help="Kit 名称，如 'Ability Kit'")
    parser.add_argument("output_path", help="输出目录")
    args = parser.parse_args()

    docs_path = Path(args.docs_path)
    output_path = Path(args.output_path)
    kit_name = args.kit_name

    # 验证文档仓路径
    ref_dir = docs_path / "zh-cn" / "application-dev" / "reference"
    if not ref_dir.exists():
        print(f"错误: 文档仓参考路径不存在 {ref_dir}", file=sys.stderr)
        sys.exit(1)

    # Step 1: 定位 Kit 目录
    kit_dir = resolve_kit_dir(kit_name, ref_dir)
    kit_readme = ref_dir / kit_dir / "Readme-CN.md"
    print(f"Kit: {kit_name} -> {kit_dir}")

    # Step 2: 解析错误码文件列表
    errorcode_files = parse_errorcode_files(kit_readme)
    if not errorcode_files:
        print(f"未在 {kit_name} 中找到错误码文档")
        sys.exit(0)

    print(f"找到 {len(errorcode_files)} 个错误码文档:")
    for f in errorcode_files:
        print(f"  - {f}")

    # Step 3: 复制文件到输出目录
    output_path.mkdir(parents=True, exist_ok=True)
    kit_full_dir = ref_dir / kit_dir

    for filename in errorcode_files:
        src = kit_full_dir / filename
        if not src.exists():
            print(f"  警告: 文件不存在 {src}，跳过", file=sys.stderr)
            continue
        dst = output_path / Path(filename).name
        shutil.copy2(src, dst)
        print(f"  已复制: {dst}")


if __name__ == "__main__":
    main()
