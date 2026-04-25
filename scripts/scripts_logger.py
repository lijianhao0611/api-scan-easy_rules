"""
logger.py - 共享日志配置模块

提供统一的 get_logger() 工厂函数，日志同时输出到控制台和文件。
根据调用者所在目录自动选择日志文件名：
  - kit-scan/ 下的脚本 -> logs/kit-scan.log
  - kit-scan-test/ 下的脚本 -> logs/kit-scan-test.log
"""

import inspect
import logging
import sys
from pathlib import Path


def get_logger(name: str) -> logging.Logger:
    """
    获取指定模块的 Logger 实例。

    首次调用时自动配置：
    - FileHandler: 输出到 {项目根}/logs/{调用者目录名}.log，级别 DEBUG
    - StreamHandler: 输出到控制台 stdout，级别 INFO

    Args:
        name: 模块名，用于日志中区分来源
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # 已初始化，避免重复添加 handler

    logger.setLevel(logging.DEBUG)

    # 日志目录：项目根目录/logs
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # 根据调用者所在目录自动选择日志文件名
    caller_dir = _detect_caller_dir()
    log_file = log_dir / f"{caller_dir}.log"

    # Formatter
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # FileHandler — 所有模块共享同一个日志文件
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # StreamHandler — 控制台保留 INFO 及以上
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


def _detect_caller_dir() -> str:
    """通过调用栈检测调用者所在的 scripts 子目录名。"""
    # 跳过自身，找第一个不在 logger.py 中的调用者
    for frame_info in inspect.stack():
        caller_path = Path(frame_info.filename).resolve()
        if caller_path.name != "logger.py":
            # 取 scripts/ 下的直接子目录名，如 kit-scan 或 kit-scan-test
            try:
                rel = caller_path.relative_to(Path(__file__).resolve().parent)
                parts = rel.parts
                if len(parts) > 1:
                    return parts[0]
            except ValueError:
                pass
            break
    return "app"
