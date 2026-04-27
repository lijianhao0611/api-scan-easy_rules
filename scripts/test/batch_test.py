"""
batch_test.py - 批量 API 审计流水线

将 API 数据按批次分组，通过 Claude Code 无头模式调用 /api-level-scan skill 进行审计，最后合并结果。
"""

import json
import subprocess
from pathlib import Path
from typing import List, Tuple, Dict, Any
import time

# ============================================================
# 可配置变量 - 修改此处即可调整脚本行为
# ============================================================

# impl_api.jsonl 文件路径（包含实现信息的 API 列表）
IMPL_API_PATH: Path = Path(__file__).parent / "impl_api.jsonl"

# api.jsonl 文件路径（仅含声明和文档的 API 列表）
API_PATH: Path = Path(__file__).parent / "api.jsonl"

# 代码仓库基础目录（包含各部件仓库的根目录）
REPO_BASE: Path = Path("/Users/spongbob/for_guance/api_dfx/DataBases")

# 批量审计结果输出根目录
OUTPUT_BASE: Path = Path(__file__).parent / "batch_results"

# 每个 batch 包含的 API 数量
BATCH_SIZE: int = 5

# 每个 batch 审计完成后，结果文件名
RESULT_FILENAME: str = "api_scan_findings.jsonl"

# 合并后的最终输出文件路径
MERGED_OUTPUT_PATH: Path = OUTPUT_BASE / "merged_api_scan_findings.jsonl"

# Claude CLI 命令名（确保在 PATH 中）
CLAUDE_CLI: str = "claude"

permisson = """ --allowedTools "Bash,Read,Edit,Find,Wc,Write" """


# ============================================================
# 函数1: 读取 impl_api.jsonl，按 impl_api_name 是否为空分组
# ============================================================

def load_and_split_impl_api(impl_api_path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    读取 impl_api.jsonl，分离 impl_api_name 为空和不为空的数据。

    Args:
        impl_api_path: impl_api.jsonl 文件路径

    Returns:
        (empty_impl_list, non_empty_impl_list)
        - empty_impl_list: impl_api_name 为空的数据列表
        - non_empty_impl_list: impl_api_name 不为空的数据列表
    """
    empty_list: List[Dict[str, Any]] = []
    non_empty_list: List[Dict[str, Any]] = []

    with open(impl_api_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            # impl_api_name 为空字符串时归入 empty_list
            if record.get("impl_api_name", "") == "":
                empty_list.append(record)
            else:
                non_empty_list.append(record)

    print(f"[函数1] 读取 impl_api.jsonl 完成: "
          f"impl_api_name 为空 {len(empty_list)} 条, "
          f"不为空 {len(non_empty_list)} 条")
    return empty_list, non_empty_list


# ============================================================
# 函数2: 从 api.jsonl 中匹配 impl_api_name 为空的数据
# ============================================================

def load_matching_api_data(
    api_path: Path,
    empty_impl_list: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    读取 api.jsonl，匹配 impl_api_name 为空的数据对应的条目。
    使用 api_declaration + module_name + declaration_file 三字段联合匹配。

    Args:
        api_path: api.jsonl 文件路径
        empty_impl_list: impl_api_name 为空的数据列表（来自函数1）

    Returns:
        匹配到的 api.jsonl 数据列表
    """
    # 构建 empty_impl_list 的匹配键集合
    match_keys = set()
    for record in empty_impl_list:
        key = (record.get("api_declaration", ""),
               record.get("module_name", ""),
               record.get("declaration_file", ""))
        match_keys.add(key)

    # 读取 api.jsonl 并匹配
    matched: List[Dict[str, Any]] = []
    with open(api_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            key = (record.get("api_declaration", ""),
                   record.get("module_name", ""),
                   record.get("declaration_file", ""))
            if key in match_keys:
                matched.append(record)

    print(f"[函数2] 从 api.jsonl 匹配到 {len(matched)} 条数据 "
          f"(待匹配 {len(empty_impl_list)} 条)")
    return matched


# ============================================================
# 函数3: 按批次分组，优先 non_empty，不足则补充 matched_api
# ============================================================

def batch_data(
    non_empty_impl: List[Dict[str, Any]],
    matched_api: List[Dict[str, Any]],
    batch_size: int = BATCH_SIZE
) -> List[List[Dict[str, Any]]]:
    """
    将数据按 batch_size 分组。优先遍历 non_empty_impl，不足时补充 matched_api。

    Args:
        non_empty_impl: impl_api_name 不为空的数据列表
        matched_api: impl_api_name 为空对应的 api.jsonl 数据列表
        batch_size: 每批次的 API 数量

    Returns:
        分组后的列表，每个元素是一个 batch（包含 batch_size 条数据）
    """
    # 合并：优先 non_empty_impl，然后 matched_api
    all_data = non_empty_impl + matched_api

    batches: List[List[Dict[str, Any]]] = []
    for i in range(0, len(all_data), batch_size):
        batch = all_data[i : i + batch_size]
        batches.append(batch)

    print(f"[函数3] 共 {len(all_data)} 条数据, "
          f"分为 {len(batches)} 个 batch (batch_size={batch_size})")
    return batches


# ============================================================
# 函数4: 为每个 batch 构建提示词
# ============================================================

def build_prompts(
    batch_list: List[List[Dict[str, Any]]],
    out_path: Path = OUTPUT_BASE,
    repo_base: Path = REPO_BASE,
    skill_name: str = "/api-level-scan"
) -> List[str]:
    """
    为每个 batch 构建调用 /api-level-scan skill 的提示词。

    Args:
        batch_list: 分组后的数据列表（来自函数3）
        out_path: 输出根目录
        repo_base: 代码仓库基础目录
        skill_name: skill 名称

    Returns:
        构建好的提示词列表
    """
    prompts: List[str] = []
    result_dirs = []

    for i, batch in enumerate(batch_list):
        # 将 batch 数据序列化为 JSONL 文本
        jsonl_lines = [json.dumps(record, ensure_ascii=False) for record in batch]
        print(f"[函数4] 构建第 {i + 1}/{len(batch_list)} 个 batch 的提示词, ")
        print(f"第1个：{jsonl_lines[0] if jsonl_lines else '空'}，第{len(jsonl_lines)}个：{jsonl_lines[-1] if jsonl_lines else '空'}")
        jsonl_text = "\n".join(jsonl_lines)

        # 每个 batch 的输出目录
        batch_out_dir = out_path / f"batch_{i}"
        result_dirs.append(str(batch_out_dir))

        # 构建提示词
        prompt = (
            f"/api-level-scan\t"
            f"api_input:{jsonl_text}\t"
            f"repo_base={repo_base}\t"
            f"out_path={batch_out_dir}\t"
        )
        
        prompts.append(prompt)

    print(f"[函数4] 构建了 {len(prompts)} 个提示词")
    return prompts,result_dirs


# ============================================================
# 函数5: 串行调用 Claude CLI 处理每个提示词
# ============================================================

def run_claude_scan(prompts: List[str]) -> List[str]:
    """
    通过 Claude CLI 无头模式串行处理每个提示词。
    参考 run_test.py 的 call_claude_cli_popen 模式。

    Args:
        prompts: 构建好的提示词列表（来自函数4）

    Returns:
        处理后的结果文件夹路径列表
    """
    result_dirs: List[str] = []

    # 从提示词中提取 out_path（每个 batch 的输出目录）
    for idx, prompt in enumerate(prompts):
        strat = time.time()
        # 提取 out_path 行
        out_dir = ""
        for line in prompt.split("\n"):
            if line.startswith("out_path="):
                out_dir = line.split("=", 1)[1]
                break

        print(f"\n[函数5] 正在处理第 {idx + 1}/{len(prompts)} 个 batch...")
        # print(f"prompt:\n{prompt}")
        print(f"  输出目录: {out_dir}")

        # 确保输出目录存在
        if out_dir:
            Path(out_dir).mkdir(parents=True, exist_ok=True)

        # 构建并执行 claude 命令
        cmd = [CLAUDE_CLI, "-p", prompt]

        try:
            # pass
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=0,
            )

            full_output: List[str] = []
            pid = process.pid
            print(f"  启动 claude 进程 PID: {pid}")

            # 实时读取输出
            while True:
                line = process.stdout.readline()
                if line:
                    print(line, end="")
                    full_output.append(line)
                if process.poll() is not None and not line:
                    break

            # 检查错误
            stderr = process.stderr.read().strip() if process.stderr else ""
            if stderr:
                print(f"  [stderr] {stderr}")

            if process.returncode != 0:
                print(f"  [错误] claude 进程退出码: {process.returncode}")
            else:
                print(f"  [完成] 第 {idx + 1} 个 batch 处理完毕")
            print(f'本次调用耗时{(time.time()-strat)}秒')
        except FileNotFoundError:
            print(f"  [错误] 未找到 claude CLI，请确认已安装并添加到 PATH")
            break
        except Exception as e:
            print(f"  [错误] 调用 claude 失败: {e}")
            break

        result_dirs.append(out_dir)

    print(f"\n[函数5] 全部完成, 共处理 {len(result_dirs)} 个 batch")
    return result_dirs


# ============================================================
# 函数6: 合并所有结果文件
# ============================================================

def merge_results(
    result_dirs: List[str],
    output_path: Path = MERGED_OUTPUT_PATH
) -> int:
    """
    将每个结果目录下的 api_scan_findings.jsonl 合并为一个文件。

    Args:
        result_dirs: 结果文件夹路径列表（来自函数5）
        output_path: 合并后的输出文件路径

    Returns:
        合并后的总行数
    """
    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_lines = 0
    with open(output_path, "w", encoding="utf-8") as out_f:
        for dir_path in result_dirs:
            if not dir_path:
                continue
            # 结果文件路径: <out_dir>/api_scan/api_scan_findings.jsonl
            result_file = Path(dir_path) / "api_scan" / RESULT_FILENAME
            if not result_file.exists():
                print(f"  [跳过] 结果文件不存在: {result_file}")
                continue

            with open(result_file, "r", encoding="utf-8") as in_f:
                for line in in_f:
                    line = line.strip()
                    if not line:
                        continue
                    out_f.write(line + "\n")
                    total_lines += 1

    print(f"[函数6] 合并完成: {total_lines} 条记录 -> {output_path}")
    return total_lines


# ============================================================
# 主流程
# ============================================================

def main():
    """执行完整的批量审计流水线"""
    print("=" * 60)
    print("批量 API 审计流水线")
    print("=" * 60)

    # 步骤1: 读取并分离 impl_api 数据
    empty_impl, non_empty_impl = load_and_split_impl_api(IMPL_API_PATH)

    # ===== 测试配置:  仅跑 test_rounds 轮 =====
    test_batch_size = 20
    test_rounds = 1

    # 步骤2: 从 api.jsonl 匹配空 impl_api_name 的数据
    matched_api = load_matching_api_data(API_PATH, empty_impl)

    # 步骤3: 按批次分组（测试用 batch_size=1）
    batches = batch_data(non_empty_impl, matched_api, test_batch_size)
    # batches = batches[:test_rounds]

    # 步骤4: 构建提示词
    prompts, result_dirs = build_prompts(batches, OUTPUT_BASE, REPO_BASE)
    
    # 步骤5: 调用 Claude 进行审计
    try:
        run_claude_scan(prompts)
    finally:
    #     # 步骤6: 合并结果
        merge_results(result_dirs, MERGED_OUTPUT_PATH)

if __name__ == "__main__":
    main()
