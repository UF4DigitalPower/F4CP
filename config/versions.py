# -*- coding: utf-8 -*-
# -------------------------------
#  @Project : F4CP
#  @Time    : 2026 - 10-31
#  @FileName: versions.py
#  @FileType: 版本管理服务，统一软件和固件的当前版本、最新版本及变更通知
#  @Software: PyCharm 2024.1.6 (Professional Edition)
#  @System  : Windows 11 23H2
#  @Author  : UF4
#  @Contact :
#  @Python  : 3.11
# -------------------------------

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from PyQt5.QtCore import QObject, pyqtSignal

from app.version import VersionComponent, VersionSnapshot, application_version, parse_version

if TYPE_CHECKING:
    from .context import AppContext


class VersionManager(QObject):
    """Version writes are explicit; downloading a package never means installing it."""

    changed = pyqtSignal(object)

    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        self._app_version = ""
        self._batch_depth = 0
        cfg = context.cfg
        self._current = {
            VersionComponent.APP: cfg.currentAppVersion,
            VersionComponent.POWER: cfg.currentPowerVersion,
            VersionComponent.UPPER: cfg.currentUpperVersion,
        }
        self._latest = {
            VersionComponent.APP: cfg.latestAppVersion,
            VersionComponent.POWER: cfg.latestPowerVersion,
            VersionComponent.UPPER: cfg.latestUpperVersion,
        }
        for item in (*self._current.values(), *self._latest.values()):
            item.valueChanged.connect(self._on_change)

    def snapshot(self) -> VersionSnapshot:
        return VersionSnapshot(
            local_app_version=self._app_version or self._current[VersionComponent.APP].value,
            latest_app_version=self._latest[VersionComponent.APP].value,
            local_lower_version=self._current[VersionComponent.POWER].value,
            latest_lower_version=self._latest[VersionComponent.POWER].value,
            local_upper_version=self._current[VersionComponent.UPPER].value,
            latest_upper_version=self._latest[VersionComponent.UPPER].value,
        )

    @contextmanager
    def batch(self):
        before = self.snapshot()
        self._batch_depth += 1
        try:
            yield
        finally:
            self._batch_depth -= 1
            after = self.snapshot()
            if self._batch_depth == 0 and before != after:
                self.changed.emit(after)

    def _on_change(self, *_):
        if self._batch_depth == 0:
            self.changed.emit(self.snapshot())

    def refresh_application(self) -> None:
        with self.batch():
            item = self._current[VersionComponent.APP]
            self._app_version = application_version(self.context.dirs.BaseDir, item.value)
            self.context.cfg.set(item, self._app_version, save=False)

    def _write(self, item, value: str, save: bool) -> None:
        parse_version(value)
        value = value.strip()
        previous = item.value
        if previous == value:
            return
        with self.batch():
            try:
                self.context.cfg.set(item, value, save=False)
                if save:
                    self.context.save()
            except Exception:
                self.context.cfg.set(item, previous, save=False)
                raise

    def set_latest(self, component: VersionComponent | str, version: str, *, save: bool = True) -> None:
        self._write(self._latest[VersionComponent(component)], version, save)

    def set_current(self, component: VersionComponent | str, version: str, *, save: bool = True) -> None:
        component = VersionComponent(component)
        if component == VersionComponent.APP:
            raise ValueError("软件当前版本由运行程序的构建元数据决定，不能通过更新检查或下载修改。")
        self._write(self._current[component], version, save)
