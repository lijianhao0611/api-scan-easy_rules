"""
batch_scan_all.py - 批量遍历所有 Kit 调用 scan_kit.py

从 kit_compont.csv 中提取去重的 Kit 名称，依次生成并执行 scan_kit.py 命令。
"""

import csv
import subprocess
import sys
from pathlib import Path

# ============================================================
# 固定配置
# ============================================================

# kit_compont.csv 路径
CSV_PATH: Path = Path(__file__).resolve().parent  / "kit_compont.csv"

# scan_kit.py 路径（同目录下）
SCAN_KIT_SCRIPT: Path = Path(__file__).resolve().parent / "scan_kit.py"

# 固定参数
JS_DECL_PATH: str = r"D:\workspace\skill易用性\interface_sdk-js"
REPO_BASE: str = r"D:\workspace\skill易用性\DataBase"
OUT_PATH: str = r"D:\workspace\skill易用性\output"
DOC_PATH:str = r"D:\workspace\skill易用性\docs"

def load_unique_kit_names(csv_path: Path) -> list[str]:
    """从 CSV 中提取去重且保持顺序的 kit 名称列表。"""
    kits: list[str] = []
    seen: set[str] = set()

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # 跳过表头 kit,component
        for row in reader:
            if not row:
                continue
            kit = row[0].strip()
            if kit and kit not in seen:
                seen.add(kit)
                kits.append(kit)

    return kits


def build_command(kit_name: str, skip_extract: bool = False) -> list[str]:
    """构建单个 Kit 的 scan_kit.py 命令。"""
    cmd = [
        sys.executable,
        str(SCAN_KIT_SCRIPT),
        "-kit", kit_name,
        "-js_decl_path", JS_DECL_PATH,
        "-repo_base", REPO_BASE,
        "-out_path", OUT_PATH,
    ]
    if skip_extract:
        cmd.append("-skip_extract")
    return cmd


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="批量遍历所有 Kit 调用 scan_kit.py")
    parser.add_argument("-n", "--dry-run", action="store_true", help="仅打印命令，不执行")
    parser.add_argument(
        "-kits",
        nargs="+",
        help="指定要扫描的 Kit 名称列表（支持子串匹配），不指定则扫描全部",
    )
    parser.add_argument(
        "-skip_extract",
        action="store_true",
        help="跳过 kit-api-extract 步骤（已有 api.jsonl 和 impl_api.jsonl 时使用）",
    )
    return parser.parse_args()


def check_paths():
    """检查关键路径是否存在，不存在则报错退出。"""
    errors = []
    if not CSV_PATH.exists():
        errors.append(f"CSV 文件不存在: {CSV_PATH}")
    if not SCAN_KIT_SCRIPT.exists():
        errors.append(f"scan_kit.py 不存在: {SCAN_KIT_SCRIPT}")
    if not Path(JS_DECL_PATH).exists():
        errors.append(f"SDK 声明目录不存在: {JS_DECL_PATH}")
    if not Path(REPO_BASE).exists():
        errors.append(f"仓库基础目录不存在: {REPO_BASE}")

    if errors:
        for e in errors:
            print(f"[错误] {e}")
        sys.exit(1)


def main():
    check_paths()
    args = parse_args()

    all_kits = load_unique_kit_names(CSV_PATH)

    # 按 -kits 参数过滤
    if args.kits:
        kits = [k for k in all_kits if any(filt.lower() in k.lower() for filt in args.kits)]
        print(f"过滤后 {len(kits)}/{len(all_kits)} 个 Kit (过滤词: {args.kits})\n")
    else:
        kits = all_kits
        print(f"共发现 {len(kits)} 个 Kit\n")

    for i, kit in enumerate(kits, 1):
        cmd = build_command(kit, args.skip_extract)
        cmd_str = " ".join(cmd)

        if args.dry_run:
            print(f"[{i}/{len(kits)}] {cmd_str}")
        else:
            print(f"\n{'=' * 60}")
            print(f"[{i}/{len(kits)}] 正在处理: {kit}")
            print(f"命令: {cmd_str}")
            print("=" * 60)

            result = subprocess.run(cmd)
            if result.returncode != 0:
                print(f"[警告] Kit '{kit}' 处理失败 (退出码: {result.returncode})，继续下一个")

    if args.dry_run:
        print(f"\n--dry-run 模式，共 {len(kits)} 条命令，未实际执行")


if __name__ == "__main__":
    main()
