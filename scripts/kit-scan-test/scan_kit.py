"""
scan_kit.py - Kit 级 API 审计流水线入口（Harness 模式）

完整流水线：
  Step 1: 调用 CLI 使用 kit-api-extract 技能提取 Kit API 数据
  Step 2: 合并数据为单个 JSONL 输入文件
  Step 3: 调用 CLI 使用 api-level-scan-test 技能进行审计
          （技能内部处理分组、并行 subagent 调度、结果合并和验证）
  Step 4: 将审计结果转为 XLSX

用法:
  python scan_kit.py -kit 'Ability Kit' -out_path 'path/to/out' \
    -js_decl_path 'path/to/interface_sdk-js' -repo_base 'path/to/database'
"""

import argparse
import json
import sys
import time
from pathlib import Path

import data_prepare
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
    kit_name: str, js_sdk_path: str, repo_base: str, output_dir: str
) -> str:
    """生成 kit-api-extract 技能的 prompt。"""
    prompt = (
        f"/kit-api-extract\n"
        f"kit_name = {kit_name}\n"
        f"js_sdk_path = {js_sdk_path}\n"
        f"databases_dir = {repo_base}\n"
        f"output_dir = {output_dir}"
    )
    return prompt


def build_scan_prompt(
    merged_input_path: str,
    repo_base: str,
    out_path: str,
    max_parallel: int = 3,
    group_strategy: str = "auto",
    group_size: int = 80,
    rule_xlsx: str = "",
    api_error_code_doc_path: str = "",
    kit_name: str = "",
) -> str:
    """生成 api-level-scan-test 技能的 prompt。"""
    prompt = (
        f"/api-level-scan-test\n"
        f"api_input={merged_input_path}\n"
        f"repo_base={repo_base}\n"
        f"out_path={out_path}\n"
        f"max_parallel={max_parallel}\n"
        f"group_strategy={group_strategy}\n"
        f"group_size={group_size}"
    )
    if rule_xlsx:
        prompt += f"\nrule_xlsx={rule_xlsx}"
    if api_error_code_doc_path:
        prompt += f"\napi_error_code_doc_path={api_error_code_doc_path}"
    if kit_name:
        prompt += f"\nkit_name={kit_name}"
    return prompt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kit 级 API DFX 审计流水线（Harness 模式）",
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
        "-repo_base", required=True, help="DataBases 目录路径（包含各部件仓库）"
    )
    parser.add_argument(
        "-max_parallel", type=int, default=3,
        help="并行审计 subagent 最大数量 (默认: 3, 范围: 1-5)"
    )
    parser.add_argument(
        "-group_strategy", default="auto",
        choices=["auto", "module", "fixed"],
        help="分组策略: module=按模块 / fixed=固定大小 / auto=自动选择 (默认: auto)"
    )
    parser.add_argument(
        "-group_size", type=int, default=80,
        help="fixed 策略下每组的 API 数量 (默认: 80)"
    )
    parser.add_argument(
        "-rule_xlsx", default="", help="规则 XLSX 文件路径（可选）"
    )
    parser.add_argument(
        "-api_error_code_doc_path", default="",
        help="API 错误码文档开源仓根目录（可选）"
    )
    parser.add_argument(
        "-skip_extract",
        action="store_true",
        help="跳过 kit-api-extract 步骤（已有 api.jsonl 和 impl_api.jsonl 时使用）",
    )
    return parser.parse_args()


def main():
    logger.info("=" * 60)
    logger.info("Kit 级 API 审计流水线（Harness 模式）")
    logger.info("=" * 60)

    args = parse_args()

    # 标准化 Kit 名称
    kit_name = normalize_kit_name(args.kit)
    output_dir = Path(args.out_path) / kit_name
    js_decl_path = Path(args.js_decl_path)
    repo_base = Path(args.repo_base).resolve()

    logger.info("Kit: %s", kit_name)
    logger.info("输出目录: %s", output_dir)
    logger.info("SDK 路径: %s", js_decl_path)
    logger.info("仓库基础: %s", repo_base)
    logger.info("分组策略: %s (group_size=%d)", args.group_strategy, args.group_size)
    logger.info("并行度: %d", args.max_parallel)

    # 验证 Kit 声明文件存在
    kit_file = resolve_kit_file(kit_name, js_decl_path)
    logger.info("Kit 声明文件: %s", kit_file)

    pipeline_start = time.time()
    step_timings: dict[str, float] = {}

    # ========================================
    # Step 1: 调用 kit-api-extract 提取 API
    # ========================================
    if not args.skip_extract:
        logger.info("=" * 60)
        logger.info("Step 1: 调用 kit-api-extract 提取 API 数据")
        logger.info("=" * 60)

        output_dir.mkdir(parents=True, exist_ok=True)
        prompt = build_extract_prompt(
            kit_name, str(js_decl_path), str(repo_base), str(output_dir)
        )
        logger.info("执行 kit-api-extract")
        t0 = time.time()
        success, _ = claude_runner.run_claude_command(prompt)
        step_timings["Step1_kit-api-extract"] = time.time() - t0
        if not success:
            logger.error("kit-api-extract 执行失败 (耗时 %.1fs)", step_timings["Step1_kit-api-extract"])
            sys.exit(1)
        logger.info("Step 1 完成，耗时 %.1fs", step_timings["Step1_kit-api-extract"])

        # 验证输出文件
        api_path = output_dir / "api.jsonl"
        impl_api_path = output_dir / "impl_api.jsonl"
        if not api_path.exists() or not impl_api_path.exists():
            logger.error("提取后未找到 api.jsonl 或 impl_api.jsonl")
            logger.error("  api.jsonl: %s (%s)", api_path, "存在" if api_path.exists() else "不存在")
            logger.error("  impl_api.jsonl: %s (%s)", impl_api_path, "存在" if impl_api_path.exists() else "不存在")
            sys.exit(1)
    else:
        logger.info("跳过 kit-api-extract 步骤 (-skip_extract)")

    # ========================================
    # Step 2: 数据准备 — 合并为单个输入文件
    # ========================================
    logger.info("=" * 60)
    logger.info("Step 2: 数据准备")
    logger.info("=" * 60)

    api_path = output_dir / "api.jsonl"
    impl_api_path = output_dir / "impl_api.jsonl"

    if not api_path.exists() or not impl_api_path.exists():
        logger.error("缺少 api.jsonl 或 impl_api.jsonl")
        sys.exit(1)

    # 加载并分离数据
    t0 = time.time()
    empty_impl, non_empty_impl = data_prepare.load_and_split_impl_api(impl_api_path)
    matched_api = data_prepare.load_matching_api_data(api_path, empty_impl)
    merged_path = data_prepare.prepare_merged_input(
        non_empty_impl, matched_api, output_dir
    )
    step_timings["Step2_数据准备"] = time.time() - t0
    logger.info("Step 2 完成，耗时 %.1fs", step_timings["Step2_数据准备"])

    # 检查合并结果是否为空
    with open(merged_path, "r", encoding="utf-8") as f:
        line_count = sum(1 for line in f if line.strip())

    if line_count == 0:
        logger.warning("合并输入为空，跳过审计步骤")
        sys.exit(0)

    # ========================================
    # Step 3: 调用 api-level-scan-test 技能
    # ========================================
    logger.info("=" * 60)
    logger.info("Step 3: 调用 api-level-scan-test 进行审计")
    logger.info("=" * 60)

    scan_prompt = build_scan_prompt(
        merged_input_path=str(merged_path.resolve()),
        repo_base=str(repo_base),
        out_path=str(output_dir.resolve()),
        max_parallel=args.max_parallel,
        group_strategy=args.group_strategy,
        group_size=args.group_size,
        rule_xlsx=args.rule_xlsx,
        api_error_code_doc_path=args.api_error_code_doc_path,
        kit_name=kit_name,
    )
    logger.info("执行 api-level-scan-test")

    t0 = time.time()
    success, _ = claude_runner.run_claude_command(scan_prompt)
    step_timings["Step3_api-level-scan-test"] = time.time() - t0
    if not success:
        logger.error("api-level-scan-test 执行失败 (耗时 %.1fs)", step_timings["Step3_api-level-scan-test"])
        sys.exit(1)
    logger.info("Step 3 完成，耗时 %.1fs", step_timings["Step3_api-level-scan-test"])

    # 检查技能输出
    findings_path = output_dir / "api_scan" / "api_scan_findings.jsonl"
    if not findings_path.exists():
        logger.warning("未找到审计结果文件: %s", findings_path)

    # 检查验证状态
    validation_path = output_dir / "api_scan" / "validation_status.json"
    if validation_path.exists():
        with open(validation_path, "r", encoding="utf-8") as f:
            status = json.load(f)
        if status.get("status") != "passed":
            logger.warning("技能验证未通过: %s", status)

    # ========================================
    # Step 4: 转换为 XLSX
    # ========================================
    logger.info("=" * 60)
    logger.info("Step 4: 转换结果为 XLSX")
    logger.info("=" * 60)

    if findings_path.exists():
        t0 = time.time()
        xlsx_path = findings_path.with_suffix(".xlsx")
        data_prepare.jsonl_to_xlsx(findings_path, xlsx_path)
        step_timings["Step4_XLSX转换"] = time.time() - t0
        logger.info("Step 4 完成，耗时 %.1fs", step_timings["Step4_XLSX转换"])
    else:
        logger.info("审计结果文件不存在，跳过 XLSX 转换")

    logger.info("=" * 60)
    logger.info("流水线执行完毕")
    total_elapsed = time.time() - pipeline_start
    logger.info("总耗时: %.1fs", total_elapsed)
    for name, dur in step_timings.items():
        logger.info("  %s: %.1fs", name, dur)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
