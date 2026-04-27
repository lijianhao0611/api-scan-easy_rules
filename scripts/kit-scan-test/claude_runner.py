"""
claude_runner.py - CLI 执行模块

封装 subprocess 调用 CLI，自动检测 claude/nga.cmd，支持单次执行，失败自动重试（最多 3 次）。
"""

import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Tuple

import sys; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts_logger import get_logger

logger = get_logger("claude_runner")


def _detect_cli() -> str:
    """自动检测可用的 CLI 命令，优先 claude，其次 nga.cmd。"""
    for cmd in ("claude", "nga.cmd"):
        if shutil.which(cmd):
            logger.info("检测到 CLI: %s", cmd)
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
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # 关键：合并 stderr，避免单独处理导致的死锁
            text=True,
            encoding="utf-8",
            bufsize=1                  # 关键：行缓冲，提升实时性
        )

        full_output: List[str] = []
        pid = process.pid
        logger.info("启动进程 PID: %s", pid)

        for line in process.stdout:
            if line:
                # stdout 透传，保留 print
                print(line, end="")
                full_output.append(line)

        process.wait()
        output = "".join(full_output)

        if process.returncode != 0:
            logger.error("进程退出码: %s", process.returncode)
            return False, output

        return True, output

    except FileNotFoundError:
        msg = "未找到命令，请确认环境配置"
        logger.error(msg)
        return False, msg
    except Exception as e:
        msg = f"执行失败: {e}"
        logger.error(msg)
        return False, msg


def run_claude_command(prompt: str) -> Tuple[bool, str]:
    """
    执行 CLI 命令，失败时自动重试（最多 3 次）。

    首次使用原始 prompt；每次重试时在 prompt 末尾追加提示语，
    告知这是重试，应基于已有数据继续执行。

    Args:
        prompt: 传递的完整 prompt

    Returns:
        (success, output) — output 包含所有尝试的累积输出
    """
    last_output: str = ""
    start = time.time()

    for attempt in range(1, MAX_RETRIES + 1):
        current_prompt = prompt if attempt == 1 else prompt + RETRY_PROMPT_SUFFIX

        if attempt > 1:
            logger.info("===== 第 %d/%d 次重试 =====", attempt, MAX_RETRIES)

        success, output = _run_once(current_prompt)
        last_output = output

        if success:
            elapsed = time.time() - start
            if attempt > 1:
                logger.info("第 %d 次尝试成功 (总耗时 %.1fs)", attempt, elapsed)
            else:
                logger.info("执行完成，耗时 %.1fs", elapsed)
            return True, output

        logger.error("第 %d/%d 次执行失败", attempt, MAX_RETRIES)

    elapsed = time.time() - start
    logger.error("已达最大重试次数 (%d)，放弃执行 (总耗时 %.1fs)", MAX_RETRIES, elapsed)
    return False, last_output
