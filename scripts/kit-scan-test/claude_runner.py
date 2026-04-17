"""
claude_runner.py - Claude CLI 执行模块

封装 subprocess 调用 Claude CLI，支持单次执行，失败自动重试（最多 3 次）。
"""

import subprocess
from pathlib import Path
from typing import List, Tuple

# Claude CLI 命令名（确保在 PATH 中）
CLAUDE_CLI: str = "claude"

# 允许的工具列表
ALLOWED_TOOLS: str = "Bash,Read,Edit,Find,Wc,Write,Search,Python,Grep,Glob,Agent"

# 最大重试次数
MAX_RETRIES: int = 3

# 重试时追加的提示语
RETRY_PROMPT_SUFFIX: str = "\n上次未执行完毕，当前是重试，请你阅读已有相关数据，再继续执行"


def _run_once(prompt: str) -> Tuple[bool, str]:
    """
    执行单次 Claude CLI 命令（无重试）。

    Args:
        prompt: 通过 -p 传递的完整 prompt

    Returns:
        (success, output)
    """
    prompt = prompt.replace("\n", "\\n")  # 确保 prompt 在命令行中正确传递
    cmd = [
        CLAUDE_CLI,
        "-p",
        prompt,
        "--allowedTools",
        ALLOWED_TOOLS,
    ]

    try:
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
        print(f"[claude_runner] 启动 claude 进程 PID: {pid}")

        # 实时读取输出
        while True:
            line = process.stdout.readline()
            if line:
                print(line, end="")
                full_output.append(line)
            if process.poll() is not None and not line:
                break

        stderr = process.stderr.read().strip() if process.stderr else ""
        if stderr:
            print(f"  [stderr] {stderr}")

        output = "".join(full_output)
        if process.returncode != 0:
            print(f"  [错误] claude 进程退出码: {process.returncode}")
            return False, output

        return True, output

    except FileNotFoundError:
        msg = "未找到 claude CLI，请确认已安装并添加到 PATH"
        print(f"  [错误] {msg}")
        return False, msg
    except Exception as e:
        msg = f"调用 claude 失败: {e}"
        print(f"  [错误] {msg}")
        return False, msg


def run_claude_command(prompt: str) -> Tuple[bool, str]:
    """
    执行 Claude CLI 命令，失败时自动重试（最多 3 次）。

    首次使用原始 prompt；每次重试时在 prompt 末尾追加提示语，
    告知 Claude 这是重试，应基于已有数据继续执行。

    Args:
        prompt: 通过 -p 传递的完整 prompt

    Returns:
        (success, output) — output 包含所有尝试的累积输出
    """
    last_output: str = ""

    for attempt in range(1, MAX_RETRIES + 1):
        current_prompt = prompt if attempt == 1 else prompt + RETRY_PROMPT_SUFFIX

        if attempt > 1:
            print(f"\n[claude_runner] ===== 第 {attempt}/{MAX_RETRIES} 次重试 =====")

        success, output = _run_once(current_prompt)
        last_output = output

        if success:
            if attempt > 1:
                print(f"[claude_runner] 第 {attempt} 次尝试成功")
            return True, output

        print(f"[claude_runner] 第 {attempt}/{MAX_RETRIES} 次执行失败")

    print(f"[claude_runner] 已达最大重试次数 ({MAX_RETRIES})，放弃执行")
    return False, last_output
