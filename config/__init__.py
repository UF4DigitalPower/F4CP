# -*- coding: utf-8 -*-
# -------------------------------
#  @Project : F4CP
#  @Time    : 2026 - 01-08 12:30
#  @FileName: __init__.py
#  @FileType: 配置包初始化文件，统一导出应用配置公共接口
#  @Software: PyCharm 2024.1.6 (Professional Edition)
#  @System  : Windows 11 23H2
#  @Author  : UF4
#  @Contact :
#  @Python  : 3.11
# -------------------------------

"""Public configuration API, shared by both legacy and focused imports."""
from . import config as _compat
from .constants import *
from .context import CTX, AppContext, AppIconPath, cfg
from .logging import configure_logging, get_logger, logger
from .paths import DirPaths
from .schema import F4CPConfig
from .storage import ConfigLoadError

__all__ = _compat.__all__


def __getattr__(name: str):
    return getattr(_compat, name)


def __dir__():
    return sorted(set(globals()) | set(__all__))
