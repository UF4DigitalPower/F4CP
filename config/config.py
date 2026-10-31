# -*- coding: utf-8 -*-
# -------------------------------
#  @Project : F4CP
#  @Time    : 2026 - 01-08 12:30
#  @FileName: config.py
#  @FileType: 配置兼容入口，保留原有导入方式并提供动态配置属性
#  @Software: PyCharm 2024.1.6 (Professional Edition)
#  @System  : Windows 11 23H2
#  @Author  : UF4
#  @Contact :
#  @Python  : 3.11
# -------------------------------

"""Compatibility facade; implementation lives in focused config submodules."""
from . import constants as _constants
from .constants import *
from .context import CTX, AppContext, AppIconPath, cfg
from .logging import configure_logging, get_logger, logger
from .paths import DirPaths
from .schema import F4CPConfig
from .storage import ConfigLoadError

__all__ = [
    "CTX", "AppContext", "DirPaths", "F4CPConfig", "cfg", "AppIconPath",
    "logger", "get_logger", "configure_logging", "ConfigLoadError",
    *_constants.__all__, *_constants.APPLICATION_EXPORTS,
]


def __getattr__(name: str):
    attribute = _constants.APPLICATION_EXPORTS.get(name)
    if attribute is not None:
        return getattr(cfg, attribute).value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(__all__))
