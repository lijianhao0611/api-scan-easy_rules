"""
batch_scan_all.py - 批量遍历所有 Kit 调用 scan_kit.py（Harness 模式）

从 kit_compont.csv 中提取去重的 Kit 名称，依次生成并执行 scan_kit.py 命令。
支持 oh/ho 双环境，自动遍历两个环境。
"""

import csv
import json
import subprocess
import sys
import time
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

# 从上级目录 config.json 读取路径配置（相对路径基于 config.json 所在目录 resolve）
_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.json"
with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
    _cfg = json.load(f)

_CONFIG_DIR = _CONFIG_PATH.parent
OUT_PATH: str = str((_CONFIG_DIR / _cfg["out_path"]).resolve())

_ENVIRONMENTS = {}
for _name in ("oh", "ho"):
    _env = _cfg.get(_name)
    if _env:
        _ENVIRONMENTS[_name] = {k: str((_CONFIG_DIR / v).resolve()) for k, v in _env.items()}


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


def load_kit_component_map(csv_path: Path) -> dict[str, list[str]]:
    """从 CSV 中加载 kit -> component 目录列表的映射。"""
    kit_map: dict[str, list[str]] = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            if not row or len(row) < 2:
                continue
            kit = row[0].strip()
            comp = row[1].strip()
            if kit and comp:
                kit_map.setdefault(kit, []).append(comp)
    return kit_map


def kit_exists_in_env(kit: str, kit_map: dict[str, list[str]], repo_base: str) -> bool:
    """检查 Kit 的任一 component 目录是否存在于当前环境的 repo_base 中。"""
    components = kit_map.get(kit, [])
    return any((Path(repo_base) / c).is_dir() for c in components)


def build_command(
    kit_name: str,
    env: dict,
    env_out_path: str,
    restart: bool = False,
    max_parallel: int = 3,
    group_strategy: str = "auto",
    group_size: int = 80,
    rule_xlsx: str = "",
) -> list[str]:
    """构建单个 Kit 的 scan_kit.py 命令。"""
    cmd = [
        sys.executable,
        str(SCAN_KIT_SCRIPT),
        "-kit", kit_name,
        "-js_decl_path", env["js_decl_path"],
        "-repo_base", env["repo_base"],
        "-out_path", env_out_path,
        "-max_parallel", str(max_parallel),
        "-group_strategy", group_strategy,
        "-group_size", str(group_size),
        "-api_error_code_doc_path", env["doc_path"],
    ]
    # c_decl_path 是可选的，只有配置中存在且不为空时才添加
    if env.get("c_decl_path"):
        cmd.extend(["-c_decl_path", env["c_decl_path"]])
    if restart:
        cmd.append("-restart")
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
        "-restart",
        action="store_true",
        help="清除已有结果，所有 Kit 从头开始（默认自动续跑）",
    )
    return parser.parse_args()


def check_paths():
    """检查关键路径是否存在，不存在则报错退出。"""
    errors = []
    if not CSV_PATH.exists():
        errors.append(f"CSV 文件不存在: {CSV_PATH}")
    if not SCAN_KIT_SCRIPT.exists():
        errors.append(f"scan_kit.py 不存在: {SCAN_KIT_SCRIPT}")

    if errors:
        for e in errors:
            logger.error(e)
        sys.exit(1)


def main():
    check_paths()
    args = parse_args()

    all_kits = load_unique_kit_names(CSV_PATH)
    kit_map = load_kit_component_map(CSV_PATH)

    # 按 -kits 参数过滤
    if args.kits:
        kits = [k for k in all_kits if any(filt.lower() in k.lower() for filt in args.kits)]
        logger.info("过滤后 %d/%d 个 Kit (过滤词: %s)", len(kits), len(all_kits), args.kits)
    else:
        kits = all_kits
        logger.info("共发现 %d 个 Kit", len(kits))

    total_start = time.time()

    for env_name, env in _ENVIRONMENTS.items():
        if not Path(env["repo_base"]).exists():
            logger.warning("环境 %s 的 repo_base 不存在，跳过: %s", env_name, env["repo_base"])
            continue
        env_out_path = str(Path(OUT_PATH) / env_name)
        logger.info("=" * 60)
        logger.info("开始处理环境: %s (输出: %s)", env_name, env_out_path)
        logger.info("=" * 60)

        env_start = time.time()
        env_success = 0
        env_fail = 0
        env_skip = 0
        env_timings: list[tuple[str, float]] = []

        for i, kit in enumerate(kits, 1):
            if not kit_exists_in_env(kit, kit_map, env["repo_base"]):
                logger.info("[%s] Kit '%s' 在此环境无 component 目录，跳过", env_name, kit)
                continue

            # 续跑模式：跳过已完成的 Kit
            if not args.restart:
                findings_path = Path(env_out_path) / kit / "api_scan" / "api_scan_findings.jsonl"
                if findings_path.exists():
                    env_skip += 1
                    logger.info("[%s][%d/%d] Kit '%s' 已完成，跳过 (结果: %s)", env_name, i, len(kits), kit, findings_path)
                    continue

            cmd = build_command(
                kit,
                env=env,
                env_out_path=env_out_path,
                restart=args.restart,
                max_parallel=args.max_parallel,
                group_strategy=args.group_strategy,
                group_size=args.group_size,
                rule_xlsx=args.rule_xlsx,
            )
            cmd_str = " ".join(cmd)

            if args.dry_run:
                logger.info("[%s][%d/%d] %s", env_name, i, len(kits), cmd_str)
            else:
                logger.info("=" * 40)
                logger.info("[%s][%d/%d] 正在处理: %s", env_name, i, len(kits), kit)
                logger.info("命令: %s", cmd_str)
                logger.info("=" * 40)

                kit_start = time.time()
                result = subprocess.run(cmd)
                kit_elapsed = time.time() - kit_start
                env_timings.append((kit, kit_elapsed))

                if result.returncode != 0:
                    env_fail += 1
                    logger.warning("Kit '%s' 处理失败 (退出码: %d, 耗时 %.1fs)，继续下一个", kit, result.returncode, kit_elapsed)
                else:
                    env_success += 1
                    logger.info("Kit '%s' 处理完成，耗时 %.1fs", kit, kit_elapsed)

        if not args.dry_run:
            env_elapsed = time.time() - env_start
            logger.info("=" * 60)
            logger.info("环境 [%s] 处理完毕: 成功 %d / 失败 %d / 跳过 %d, 总耗时 %.1fs, 平均 %.1fs/Kit",
                        env_name, env_success, env_fail, env_skip, env_elapsed,
                        env_elapsed / len(env_timings) if env_timings else 0)
            for kit_name, dur in env_timings:
                logger.info("  %s: %.1fs", kit_name, dur)
            logger.info("=" * 60)

    if args.dry_run:
        logger.info("--dry-run 模式，共 %d 条命令，未实际执行", len(kits))
    else:
        total_elapsed = time.time() - total_start
        logger.info("=" * 60)
        logger.info("全部环境处理完毕，总耗时 %.1fs", total_elapsed)
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
