# -*- coding: utf-8 -*-
# -------------------------------
#  @Project : F4CP
#  @Time    : 2026 - 01-08 12:30
#  @FileName: logging.py
#  @FileType: 日志配置模块，负责日志初始化、格式化和日志器获取
#  @Software: PyCharm 2024.1.6 (Professional Edition)
#  @System  : Windows 11 23H2
#  @Author  : UF4
#  @Contact :
#  @Python  : 3.11
# -------------------------------

"""Configure the application logger once without interfering with root handlers."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger("F4CP")
_lock = threading.Lock()
_FORMAT = "[%(asctime)s] [%(threadName)s/%(levelname)s] [%(name)s]: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class ConsoleFormatter(logging.Formatter):
    """Omit traceback details on the console while retaining them in the file."""

    def format(self, record: logging.LogRecord) -> str:
        original = record.exc_info, record.exc_text, record.stack_info
        try:
            record.exc_info = record.exc_text = record.stack_info = None
            return super().format(record)
        finally:
            record.exc_info, record.exc_text, record.stack_info = original


def get_logger(name: str) -> logging.Logger:
    return logger.getChild(name)


def configure_logging(log_dir: str | Path) -> logging.Logger:
    """Install only our own handlers; defer opening a file until the first log."""
    with _lock:
        if any(getattr(handler, "_f4cp_handler", False) for handler in logger.handlers):
            return logger
        directory = Path(log_dir)
        directory.mkdir(parents=True, exist_ok=True)
        console = logging.StreamHandler()
        console.setFormatter(ConsoleFormatter(_FORMAT, datefmt=_DATE_FORMAT))
        file_handler = logging.FileHandler(
            directory / f"f4cp_{time.strftime('%Y%m%d_%H%M%S')}.log",
            mode="a", encoding="utf-8", delay=True,
        )
        file_handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))
        for handler in (console, file_handler):
            handler.setLevel(logging.DEBUG)
            handler._f4cp_handler = True
            logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        return logger
