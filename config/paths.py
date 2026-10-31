# -*- coding: utf-8 -*-
# -------------------------------
#  @Project : F4CP
#  @Time    : 2026 - 01-08 12:30
#  @FileName: paths.py
#  @FileType: 路径配置模块，负责源码和打包环境下的目录解析
#  @Software: PyCharm 2024.1.6 (Professional Edition)
#  @System  : Windows 11 23H2
#  @Author  : UF4
#  @Contact :
#  @Python  : 3.11
# -------------------------------

"""Application paths for source checkouts and cx_Freeze distributions."""
from __future__ import annotations

import sys
from functools import cached_property
from pathlib import Path


def _detect_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


class DirPaths:
    """Create resource directories on first access; retain the established path API."""

    def __init__(self, base_dir: str | Path | None = None):
        self._base = Path(base_dir).expanduser().resolve() if base_dir is not None else _detect_base_dir()

    def _ensure_dir(self, *parts: str) -> Path:
        directory = self._base.joinpath(*parts)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @cached_property
    def BaseDir(self) -> Path:
        return self._base

    @cached_property
    def ResourcesDir(self) -> Path:
        return self._ensure_dir("src")

    @cached_property
    def AssetsDir(self) -> Path:
        return self._ensure_dir("src", "assets")

    @cached_property
    def ConfigDir(self) -> Path:
        return self._ensure_dir("src", "config")

    @cached_property
    def ConfigJsonPath(self) -> Path:
        return self.ConfigDir / "config.json"

    @cached_property
    def ThemeDir(self) -> Path:
        return self._ensure_dir("src", "theme")

    @cached_property
    def FontDir(self) -> Path:
        return self._ensure_dir("src", "font")

    @cached_property
    def LogDir(self) -> Path:
        return self._ensure_dir("logs")

    @cached_property
    def ToolsDir(self) -> Path:
        return self._ensure_dir("src", "tools")

    @cached_property
    def McuPackDir(self) -> Path:
        return self._ensure_dir("src", "tools", "pack")

    @cached_property
    def FirmwareDir(self) -> Path:
        return self._ensure_dir("src", "firmware")

    @cached_property
    def FirmwarePowerDir(self) -> Path:
        return self._ensure_dir("src", "firmware", "power")

    @property
    def FirmwarePower(self) -> Path:
        return self.FirmwarePowerDir

    @cached_property
    def FirmwareUpperDir(self) -> Path:
        return self._ensure_dir("src", "firmware", "upper")

    @property
    def FirmwareUpper(self) -> Path:
        return self.FirmwareUpperDir

    @cached_property
    def AppIconPath(self) -> str:
        return str(self.AssetsDir / "F4CP_ICO_256.ico")

    @cached_property
    def Uf4TargetExeDir(self) -> Path:
        return self.ToolsDir / "uf4-target"
