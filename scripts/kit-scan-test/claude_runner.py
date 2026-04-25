"""
claude_runner.py - Claude CLI 执行模块

封装 subprocess 调用 Claude CLI，支持单次执行，失败自动重试（最多 3 次）。
"""

import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple


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

# 最大重试次数
MAX_RETRIES: int = 3

# 重试时追加的提示语
RETRY_PROMPT_SUFFIX: str = "\n上次未执行完毕，当前是重试，请你阅读已有相关数据，再继续执行"


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


def _run_once(prompt: str) -> Tuple[bool, str]:
    """
    执行单次 CLI 命令（无重试）。

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
