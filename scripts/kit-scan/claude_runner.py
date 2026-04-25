"""
claude_runner.py - Claude CLI 执行模块

封装 subprocess 调用 Claude CLI，支持单次执行和批量扫描。
"""

import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Tuple, Callable


def _detect_cli() -> str:
    """自动检测可用的 CLI 命令，优先 claude，其次 nga.cmd。"""
    for cmd in ("claude", "nga.cmd"):
        if shutil.which(cmd):
            print(f"[claude_runner] 检测到 CLI: {cmd}")
            return cmd
    raise RuntimeError("未找到 claude 或 nga 命令，请确认已安装并加入 PATH")


CLAUDE_CLI: str = _detect_cli()

# 允许的工具列表（仅 claude 使用）
ALLOWED_TOOLS: str = "Bash,Read,Edit,Find,Wc,Write,Search,Python,Grep,Glob,Agent"


def _build_cmd(prompt: str) -> List[str]:
    """根据检测到的 CLI 类型构建命令行参数。"""
    if CLAUDE_CLI == "claude":
        prompt = prompt.replace("\n", "\\n")
        return [
            CLAUDE_CLI,
            "-p",
            prompt,
            "--allowedTools",
            ALLOWED_TOOLS,
        ]
    else:
        # nga: ["nga.cmd", "run", prompt, "--thinking"]
        return [
            CLAUDE_CLI,
            "run",
            prompt,
            "--thinking",
        ]


def run_claude_command(prompt: str) -> Tuple[bool, str]:
    """
    执行单次 CLI 命令。

    Args:
        prompt: 传递的完整 prompt

    Returns:
        (success, output)
    """
    cmd = _build_cmd(prompt)

    try:
        # --- 核心优化点 ---
        # 1. stderr=subprocess.STDOUT: 将错误流合并到标准输出，防止 stderr 管道填满导致死锁
        # 2. encoding="cp936": Windows 命令行默认编码是 GBK (cp936)，设为 utf-8 极易导致解码阻塞或乱码
        # 3. bufsize=1: 行缓冲，配合 text=True 确保 readline 能更快获取数据
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # 关键：合并 stderr，避免单独处理导致的死锁
            text=True,
            encoding="utf-8",          # 关键：Windows 中文环境通常使用 cp936 (GBK)
            bufsize=1                  # 关键：行缓冲，提升实时性
        )

        full_output: List[str] = []
        pid = process.pid
        print(f"[claude_runner] 启动进程 PID: {pid}")

        # --- 实时读取优化 ---
        # 直接迭代 stdout 对象，比 while+readline 更符合 Python 风格且高效
        # 注意：因为 stderr 已合并到 stdout，这里能读到所有输出
        for line in process.stdout:
            if line:
                # end="" 是因为读取的行通常自带换行符
                print(line, end="") 
                full_output.append(line)

        # 等待进程彻底结束并获取返回码
        process.wait()

        # 因为 stderr 已合并，这里不需要单独读取 stderr
        output = "".join(full_output)
        
        if process.returncode != 0:
            print(f"\n[错误] 进程退出码: {process.returncode}")
            return False, output

        return True, output

    except FileNotFoundError:
        msg = "未找到命令，请确认环境配置"
        print(f"[错误] {msg}")
        return False, msg
    except Exception as e:
        msg = f"执行失败: {e}"
        print(f"[错误] {msg}")
        return False, msg


def run_batch_scan(
    batch_paths: List[Path],
    output_dir: Path,
    repo_base: Path,
    build_prompt_fn: Callable[[Path, Path, Path], str],
    result_filename: str = "api_scan_findings.jsonl",
) -> None:
    """
    遍历每个 batch 文件，构建 prompt 并调用 Claude CLI 执行审计。
    若某个 batch 的结果文件已存在，则跳过该批次。

    Args:
        batch_paths: batch JSONL 输入文件路径列表
        output_dir: Kit 输出根目录
        repo_base: DataBases 目录路径
        build_prompt_fn: 构建 prompt 的回调函数 (batch_path, batch_out_dir, repo_base) -> str
        result_filename: 结果文件名，用于判断是否已存在
    """
    batch_result_dir = output_dir / "batch_result"
    total = len(batch_paths)
    skipped = 0

    for idx, batch_path in enumerate(batch_paths):
        batch_out_dir = batch_result_dir / f"batch_{idx}"

        # 检查该批次结果是否已存在
        result_file = batch_out_dir / "api_scan" / result_filename
        if result_file.exists():
            skipped += 1
            print(f"\n[claude_runner] 跳过 batch {idx + 1}/{total} (结果已存在: {result_file})")
            continue

        batch_out_dir.mkdir(parents=True, exist_ok=True)
        prompt = build_prompt_fn(batch_path, batch_out_dir, repo_base)

        print(f"\n{'=' * 50}")
        print(f"[claude_runner] 处理 batch {idx + 1}/{total}")
        print(f"  输入: {batch_path}")
        print(f"  输出: {batch_out_dir}")

        start = time.time()
        success, _ = run_claude_command(prompt)
        elapsed = time.time() - start

        if success:
            print(f"  [完成] 耗时 {elapsed:.1f}s")
        else:
            print(f"  [失败] 耗时 {elapsed:.1f}s，继续处理下一个 batch")

    print(f"\n[claude_runner] 全部 batch 处理完毕: {total} 个 (跳过 {skipped} 个已有结果)")
