"""
scan_kit.py - Kit 级 API 审计流水线入口

完整流水线：
  Step 1: 调用 CLI 使用 kit-api-extract 技能提取 Kit API 数据
  Step 2: 按批次调用 CLI 使用 api-level-scan 技能进行审计
  Step 3: 合并审计结果

用法:
  python scan_kit.py -kit 'Ability Kit' -out_path 'path/to/out' \
    -js_decl_path 'path/to/interface_sdk-js' -repo_base 'path/to/database'
"""

import argparse
import shutil
import sys
import time
from pathlib import Path

import batch_pipeline
import claude_runner

import sys; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts_logger import get_logger

logger = get_logger("scan_kit")


def normalize_kit_name(raw_name: str) -> str:
    """
    标准化 Kit 名称。
    "Ability Kit" -> "AbilityKit"
    "AbilityKit" -> "AbilityKit" (幂等)
    """
    return raw_name.replace(" ", "")


def resolve_kit_file(kit_name: str, js_sdk_path: Path) -> Path:
    """
    查找 Kit 声明文件，依次尝试 .d.ts / .d.ets / .static.d.ets。

    Raises:
        FileNotFoundError: 所有扩展名均未找到
    """
    candidates = [
        js_sdk_path / "kits" / f"@kit.{kit_name}.d.ts",
        js_sdk_path / "kits" / f"@kit.{kit_name}.d.ets",
        js_sdk_path / "kits" / f"@kit.{kit_name}.static.d.ets",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        f"找不到 Kit 声明文件: @kit.{kit_name}.d.ts/.d.ets\n"
        f"已搜索: {[str(c) for c in candidates]}"
    )


def build_extract_prompt(
    kit_name: str, js_sdk_path: str, repo_base: str, output_dir: str,
    c_sdk_path: str = ""
) -> str:
    """生成 kit-api-extract 技能的 prompt。"""
    prompt = (
        f"/kit-api-extract\t"
        f"kit_name = {kit_name}\t"
        f"js_sdk_path = {js_sdk_path}\t"
        f"databases_dir = {repo_base}\t"
        f"output_dir = {output_dir}\t"
    )
    if c_sdk_path:
        prompt += f"c_sdk_path = {c_sdk_path}\t"
    return prompt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kit 级 API DFX 审计流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-kit", required=True, help='Kit 名称，如 "Ability Kit" 或 "AbilityKit"'
    )
    parser.add_argument(
        "-out_path", required=True, help="输出根目录"
    )
    parser.add_argument(
        "-js_decl_path", required=True, help="interface_sdk-js 目录路径"
    )
    parser.add_argument(
        "-c_decl_path", default="", help="interface_sdk-c 目录路径（可选）"
    )
    parser.add_argument(
        "-repo_base", required=True, help="DataBases 目录路径（包含各部件仓库）"
    )
    parser.add_argument(
        "-batch_size", type=int, default=20, help="每个 batch 包含的 API 数量 (默认: 20)"
    )
    parser.add_argument(
        "-restart",
        action="store_true",
        help="清除已有输出目录，从头开始（默认自动续跑）",
    )
    return parser.parse_args()


def main():
    logger.info("=" * 60)
    logger.info("Kit 级 API 审计流水线")
    logger.info("=" * 60)

    args = parse_args()

    # 标准化 Kit 名称
    kit_name = normalize_kit_name(args.kit)
    output_dir = Path(args.out_path) / kit_name
    js_decl_path = Path(args.js_decl_path)
    c_decl_path = args.c_decl_path  # 可选，可能为空字符串
    repo_base = Path(args.repo_base).resolve()

    logger.info("Kit: %s", kit_name)
    logger.info("输出目录: %s", output_dir)
    logger.info("SDK 路径: %s", js_decl_path)
    if c_decl_path:
        logger.info("C SDK 路径: %s", c_decl_path)
    logger.info("仓库基础: %s", repo_base)
    logger.info("Batch 大小: %d", args.batch_size)

    # -restart 模式：清除已有输出目录
    if args.restart:
        if output_dir.exists():
            shutil.rmtree(output_dir)
            logger.info("-restart 模式，已清除输出目录: %s", output_dir)
    else:
        logger.info("续跑模式（自动跳过已完成步骤）")

    # 验证 Kit 声明文件存在
    kit_file = resolve_kit_file(kit_name, js_decl_path)
    logger.info("Kit 声明文件: %s", kit_file)

    pipeline_start = time.time()
    step_timings: dict[str, float] = {}

    # ========================================
    # Step 1: 调用 kit-api-extract 提取 API
    # ========================================
    api_path = output_dir / "api.jsonl"
    impl_api_path = output_dir / "impl_api.jsonl"

    # 自动检测：若两个文件均存在则跳过 Step 1（除非 -restart 已清除）
    skip_step1 = api_path.exists() and impl_api_path.exists()

    if skip_step1:
        logger.info("检测到已有 api.jsonl 和 impl_api.jsonl，跳过 Step 1")
    else:
        logger.info("=" * 60)
        logger.info("Step 1: 调用 kit-api-extract 提取 API 数据")
        logger.info("=" * 60)

        output_dir.mkdir(parents=True, exist_ok=True)
        prompt = build_extract_prompt(
            kit_name, str(js_decl_path), str(repo_base), str(output_dir),
            c_sdk_path=c_decl_path
        )

        t0 = time.time()
        success, _ = claude_runner.run_claude_command(prompt)
        step_timings["Step1_kit-api-extract"] = time.time() - t0
        if not success:
            logger.error("kit-api-extract 执行失败 (耗时 %.1fs)", step_timings["Step1_kit-api-extract"])
            sys.exit(1)
        logger.info("Step 1 完成，耗时 %.1fs", step_timings["Step1_kit-api-extract"])

        # 验证输出文件
        if not api_path.exists() or not impl_api_path.exists():
            logger.error("提取后未找到 api.jsonl 或 impl_api.jsonl")
            logger.error("  api.jsonl: %s (%s)", api_path, "存在" if api_path.exists() else "不存在")
            logger.error("  impl_api.jsonl: %s (%s)", impl_api_path, "存在" if impl_api_path.exists() else "不存在")
            sys.exit(1)

    # ========================================
    # Step 2: 批量审计
    # ========================================
    logger.info("=" * 60)
    logger.info("Step 2: 批量 API 审计")
    logger.info("=" * 60)

    if not api_path.exists() or not impl_api_path.exists():
        logger.error("缺少 api.jsonl 或 impl_api.jsonl")
        sys.exit(1)

    # 加载数据并分批
    empty_impl, non_empty_impl = batch_pipeline.load_and_split_impl_api(impl_api_path)
    matched_api = batch_pipeline.load_matching_api_data(api_path, empty_impl)
    batch_paths = batch_pipeline.prepare_batches(
        non_empty_impl, matched_api, args.batch_size, output_dir
    )

    if not batch_paths:
        logger.warning("没有数据需要处理")
        sys.exit(0)

    # 检测是否所有 batch 都已完成
    batch_result_dir = output_dir / "batch_result"
    all_batches_done = all(
        (batch_result_dir / f"batch_{idx}" / "api_scan" / "api_scan_findings.jsonl").exists()
        for idx in range(len(batch_paths))
    )

    if all_batches_done:
        logger.info("所有 %d 个 batch 结果已存在，跳过 Step 2", len(batch_paths))
    else:
        # 执行批量审计
        t0 = time.time()
        claude_runner.run_batch_scan(
            batch_paths, output_dir, repo_base, batch_pipeline.build_scan_prompt
        )
        step_timings["Step2_批量审计"] = time.time() - t0
        logger.info("Step 2 完成，耗时 %.1fs", step_timings["Step2_批量审计"])

    # Step 3: 合并结果（始终执行）
    t0 = time.time()
    merged_path = output_dir / "batch_result" / "merged_api_scan_findings.jsonl"
    batch_pipeline.merge_batch_results(output_dir, merged_path)

    # 将合并结果转为 XLSX
    if merged_path.exists():
        xlsx_path = merged_path.with_suffix(".xlsx")
        batch_pipeline.jsonl_to_xlsx(merged_path, xlsx_path)
    step_timings["结果合并与XLSX转换"] = time.time() - t0

    logger.info("=" * 60)
    logger.info("流水线执行完毕")
    total_elapsed = time.time() - pipeline_start
    logger.info("总耗时: %.1fs", total_elapsed)
    for name, dur in step_timings.items():
        logger.info("  %s: %.1fs", name, dur)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
