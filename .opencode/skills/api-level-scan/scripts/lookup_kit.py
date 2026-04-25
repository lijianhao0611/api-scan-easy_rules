#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kit-Component 映射查询脚本
根据部件名称查询所属的 Kit
"""

import os
import csv
import argparse
from typing import Optional, Dict

# 获取脚本所在目录，用于定位 assets 目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)

# 默认的映射文件路径 (优先使用 skill 内的 assets 目录)
DEFAULT_MAPPING_FILE = os.path.join(SKILL_DIR, "assets", "kit_compont.csv")


def load_kit_component_mapping(mapping_file: str = DEFAULT_MAPPING_FILE) -> Dict[str, str]:
    """
    加载 Kit-Component 映射关系

    Args:
        mapping_file: 映射文件路径 (CSV格式)

    Returns:
        component -> kit 的映射字典
    """
    component_to_kit = {}

    if not os.path.exists(mapping_file):
        return component_to_kit

    with open(mapping_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 兼容不同的列名 (kit/compoent 或 kit/component)
            kit = row.get('kit', '').strip()
            component = row.get('compoent', '') or row.get('component', '')
            component = component.strip()

            if kit and component:
                component_to_kit[component] = kit

    return component_to_kit


def lookup_kit(component_name: str, mapping_file: str = DEFAULT_MAPPING_FILE) -> Optional[str]:
    """
    根据部件名称查询所属的 Kit

    Args:
        component_name: 部件名称
        mapping_file: 映射文件路径

    Returns:
        Kit 名称，如果未找到返回 None
    """
    component_to_kit = load_kit_component_mapping(mapping_file)

    # 直接匹配
    if component_name in component_to_kit:
        return component_to_kit[component_name]

    # 尝试模糊匹配 (部件名可能包含路径前缀)
    component_basename = os.path.basename(component_name)
    if component_basename in component_to_kit:
        return component_to_kit[component_basename]

    # 尝试反向匹配 (映射表中的部件名可能是简写)
    for mapped_component, kit in component_to_kit.items():
        if mapped_component in component_name or component_name in mapped_component:
            return kit

    return None


def get_all_components_for_kit(kit_name: str, mapping_file: str = DEFAULT_MAPPING_FILE) -> list:
    """
    获取指定 Kit 下的所有部件

    Args:
        kit_name: Kit 名称
        mapping_file: 映射文件路径

    Returns:
        部件名称列表
    """
    component_to_kit = load_kit_component_mapping(mapping_file)
    return [comp for comp, kit in component_to_kit.items() if kit == kit_name]


def main():
    parser = argparse.ArgumentParser(
        description="Lookup Kit by component name"
    )
    parser.add_argument("component", help="Component name to lookup")
    parser.add_argument(
        "-f", "--file",
        default=DEFAULT_MAPPING_FILE,
        help=f"Mapping file path (default: {DEFAULT_MAPPING_FILE})"
    )
    parser.add_argument(
        "-l", "--list",
        action="store_true",
        help="List all components for the kit instead of looking up"
    )

    args = parser.parse_args()

    if args.list:
        components = get_all_components_for_kit(args.component, args.file)
        if components:
            print(f"Components in kit '{args.component}':")
            for comp in sorted(components):
                print(f"  - {comp}")
        else:
            print(f"No components found for kit '{args.component}'")
    else:
        kit = lookup_kit(args.component, args.file)
        if kit:
            print(f"Component '{args.component}' belongs to kit: {kit}")
        else:
            print(f"Kit not found for component '{args.component}'")
            print("Please provide the kit name manually.")


if __name__ == "__main__":
    main()
