"""
batch_scan_all.py - 批量遍历所有 Kit 调用 scan_kit.py（Harness 模式）

从 kit_compont.csv 中提取去重的 Kit 名称，依次生成并执行 scan_kit.py 命令。
"""

import csv
import subprocess
import sys
from pathlib import Path

import sys; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts_logger import get_logger

logger = get_logger("batch_scan_all")

# ============================================================
# 固定配置
# ============================================================

# kit_compont.csv 路径
CSV_PATH: Path = Path(__file__).resolve().parent.parent / "kit_compont.csv"

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


def build_command(
    kit_name: str,
    skip_extract: bool = False,
    max_parallel: int = 3,
    group_strategy: str = "auto",
    group_size: int = 80,
    rule_xlsx: str = "",
    api_error_code_doc_path: str = "",
) -> list[str]:
    """构建单个 Kit 的 scan_kit.py 命令。"""
    cmd = [
        sys.executable,
        str(SCAN_KIT_SCRIPT),
        "-kit", kit_name,
        "-js_decl_path", JS_DECL_PATH,
        "-repo_base", REPO_BASE,
        "-out_path", OUT_PATH,
        "-max_parallel", str(max_parallel),
        "-group_strategy", group_strategy,
        "-group_size", str(group_size),
        "-api_error_code_doc_path", api_error_code_doc_path,
    ]
    if skip_extract:
        cmd.append("-skip_extract")
    if rule_xlsx:
        cmd.extend(["-rule_xlsx", rule_xlsx])
    return cmd


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="批量遍历所有 Kit 调用 scan_kit.py（Harness 模式）")
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
    parser.add_argument(
        "-max_parallel", type=int, default=3,
        help="并行审计 subagent 最大数量 (默认: 3)"
    )
    parser.add_argument(
        "-group_strategy", default="auto",
        choices=["auto", "module", "fixed"],
        help="分组策略 (默认: auto)"
    )
    parser.add_argument(
        "-group_size", type=int, default=80,
        help="fixed 策略下每组的 API 数量 (默认: 80)"
    )
    parser.add_argument(
        "-rule_xlsx", default="",
        help="规则 XLSX 文件路径"
    )
    parser.add_argument(
        "-api_error_code_doc_path", default=DOC_PATH,
        help="API 错误码文档开源仓根目录"
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
            logger.error(e)
        sys.exit(1)


def main():
    check_paths()
    args = parse_args()

    all_kits = load_unique_kit_names(CSV_PATH)

    # 按 -kits 参数过滤
    if args.kits:
        kits = [k for k in all_kits if any(filt.lower() in k.lower() for filt in args.kits)]
        logger.info("过滤后 %d/%d 个 Kit (过滤词: %s)", len(kits), len(all_kits), args.kits)
    else:
        kits = all_kits
        logger.info("共发现 %d 个 Kit", len(kits))

    for i, kit in enumerate(kits, 1):
        cmd = build_command(
            kit,
            skip_extract=args.skip_extract,
            max_parallel=args.max_parallel,
            group_strategy=args.group_strategy,
            group_size=args.group_size,
            rule_xlsx=args.rule_xlsx,
            api_error_code_doc_path=args.api_error_code_doc_path,
        )
        cmd_str = " ".join(cmd)

        if args.dry_run:
            logger.info("[%d/%d] %s", i, len(kits), cmd_str)
        else:
            logger.info("=" * 60)
            logger.info("[%d/%d] 正在处理: %s", i, len(kits), kit)
            logger.info("命令: %s", cmd_str)
            logger.info("=" * 60)

            result = subprocess.run(cmd)
            if result.returncode != 0:
                logger.warning("Kit '%s' 处理失败 (退出码: %d)，继续下一个", kit, result.returncode)

    if args.dry_run:
        logger.info("--dry-run 模式，共 %d 条命令，未实际执行", len(kits))


if __name__ == "__main__":
    main()
