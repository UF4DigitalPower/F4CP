# -*- coding: utf-8 -*-
# -------------------------------
#  @Project : F4CP
#  @Time    : 2026 - 01-08 12:30
#  @FileName: context.py
#  @FileType: 应用配置上下文，负责配置实例、加载、重载和保存入口
#  @Software: PyCharm 2024.1.6 (Professional Edition)
#  @System  : Windows 11 23H2
#  @Author  : UF4
#  @Contact :
#  @Python  : 3.11
# -------------------------------

"""Application context and the single runtime configuration instance."""
from __future__ import annotations

from pathlib import Path

from .logging import configure_logging, get_logger
from .paths import DirPaths
from .schema import F4CPConfig, bind_global_config
from .storage import ConfigLoadError, JsonConfigStore
from .versions import VersionManager

_log = get_logger("Config")


class AppContext:
    """Own one configuration file and its paths; injected contexts stay independent."""

    def __init__(self, *, base_dir: str | Path | None = None,
                 init_logging: bool = True, bind_global: bool = False):
        self._dirs = DirPaths(base_dir)
        if init_logging:
            configure_logging(self._dirs.LogDir)
        self._qconfig = F4CPConfig()
        self._qconfig.file = self._dirs.ConfigJsonPath
        self._versions = VersionManager(self)
        self.last_load_error: OSError | ConfigLoadError | None = None
        if not self._qconfig.file.exists():
            JsonConfigStore(self._qconfig.file).write({})
        self.reload()
        if bind_global:
            bind_global_config(self._qconfig)

    @property
    def dirs(self) -> DirPaths:
        return self._dirs

    @property
    def cfg(self) -> F4CPConfig:
        return self._qconfig

    @property
    def qcfg(self) -> F4CPConfig:
        """Compatibility alias for cfg."""
        return self._qconfig

    @property
    def app_icon_path(self) -> str:
        return self._dirs.AppIconPath

    @property
    def versions(self) -> VersionManager:
        return self._versions

    def reload(self) -> bool:
        """Reload in place, retaining signals and settings if the file is invalid."""
        try:
            with self._versions.batch():
                self._qconfig.load()
                self._versions.refresh_application()
        except (OSError, ConfigLoadError) as exc:
            self.last_load_error = exc
            _log.warning("Could not reload configuration: %s", exc)
            return False
        self.last_load_error = None
        return True

    def save(self) -> None:
        self._qconfig.save()


CTX = AppContext(bind_global=True)
cfg = CTX.cfg
version_manager = CTX.versions
AppIconPath = CTX.app_icon_path
