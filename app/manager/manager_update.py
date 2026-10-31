# -*- coding: utf-8 -*-
# -------------------------------
#  @Project : F4CP
#  @Time    : 2026 - 10-31
#  @FileName: manager_update.py
#  @FileType: 软件更新管理器，负责异步检查、版本缓存同步和下载任务
#  @Software: PyCharm 2024.1.6 (Professional Edition)
#  @System  : Windows 11 23H2
#  @Author  : UF4
#  @Contact :
#  @Python  : 3.11
# -------------------------------

"""Qt bridge for GitHub software updates; network and disk I/O run off the GUI thread."""
from __future__ import annotations

import threading
import weakref
from dataclasses import dataclass, field, replace
from pathlib import Path

from PyQt5 import sip
from PyQt5.QtCore import QCoreApplication, QEvent, QObject, Qt, pyqtSignal

from app.core.github_release import (
    DownloadCancelled,
    ReleaseAsset,
    SoftwareRelease,
    compatible_assets,
    download_asset,
    fetch_release,
    network_error,
)
from app.version import VersionComponent, VersionSnapshot
from config import CTX, get_logger

logger = get_logger("SoftwareUpdate")


@dataclass(frozen=True)
class UpdateCheckResult:
    success: bool = False
    manual: bool = True
    has_changes: bool = False
    message: str = ""
    snapshot: VersionSnapshot = field(default_factory=VersionSnapshot)
    release_tag: str = ""
    release_url: str = ""
    release_notes: str = ""
    release: SoftwareRelease | None = None


@dataclass(frozen=True)
class AppDownloadResult:
    success: bool = False
    cancelled: bool = False
    message: str = ""
    path: Path | None = None


class UpdateCheckFinishedEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, result: UpdateCheckResult):
        super().__init__(self.EVENT_TYPE)
        self.result = result


class UpdateManager(QObject):
    checkFinished = pyqtSignal(object)
    downloadProgress = pyqtSignal(object, object)
    downloadFinished = pyqtSignal(object)
    stateChanged = pyqtSignal()
    versionsChanged = pyqtSignal(object)
    _checkReady = pyqtSignal(object)
    _downloadReady = pyqtSignal(object)

    def __init__(self, context=CTX):
        super().__init__()
        self.context = context
        self.versions = context.versions
        self.versions.changed.connect(self.versionsChanged)
        self.is_checking = False
        self.is_downloading = False
        self.latest_release: SoftwareRelease | None = None
        self.last_download: Path | None = None
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self._cancel = threading.Event()
        self._check_target = None
        self._checkReady.connect(self._finish_check, Qt.QueuedConnection)
        self._downloadReady.connect(self._finish_download, Qt.QueuedConnection)

    def get_cached_versions(self) -> VersionSnapshot:
        return self.versions.snapshot()

    def check_for_updates(self, parent=None, manual: bool = True) -> bool:
        if self.is_checking or self.is_downloading:
            return False
        self.is_checking = True
        self._check_target = weakref.ref(parent) if parent is not None else None
        self.latest_release = None
        cfg = self.context.cfg
        repository = cfg.updateUrl.value
        include_prereleases = cfg.includePrereleases.value
        snapshot = self.get_cached_versions()
        self.stateChanged.emit()

        def run():
            try:
                release = fetch_release(repository, include_prereleases)
                updated = snapshot.with_latest(VersionComponent.APP, release.tag)
                result = UpdateCheckResult(
                    success=True, manual=manual,
                    has_changes=updated.app.has_update,
                    snapshot=updated, message=updated.app.message,
                    release_tag=release.tag, release_url=release.url, release_notes=release.notes, release=release,
                )
            except Exception as exc:
                logger.warning("Software update check failed: %s", exc)
                result = UpdateCheckResult(manual=manual, message=network_error(exc), snapshot=snapshot)
            self._checkReady.emit(result)

        threading.Thread(target=run, name="F4CP-UpdateCheck", daemon=True).start()
        return True

    def _finish_check(self, result: UpdateCheckResult) -> None:
        self.is_checking = False
        self.latest_release = result.release if result.success else None
        if result.success:
            try:
                self.versions.set_latest(VersionComponent.APP, result.release_tag)
            except (OSError, ValueError) as exc:
                logger.warning("Could not save latest software version: %s", exc)
                self.versions.set_latest(VersionComponent.APP, result.release_tag, save=False)
            snapshot = self.versions.snapshot()
            result = replace(result, snapshot=snapshot, has_changes=snapshot.app.has_update,
                             message=snapshot.app.message)
        target = self._check_target() if self._check_target else None
        self._check_target = None
        self.stateChanged.emit()
        self.checkFinished.emit(result)
        if target is not None and not sip.isdeleted(target):
            QCoreApplication.postEvent(target, UpdateCheckFinishedEvent(result))

    def download_update(self, asset: ReleaseAsset, destination: Path) -> bool:
        if self.is_downloading or self.is_checking or self.latest_release is None:
            return False
        current = self.versions.snapshot().app
        if not current.has_update or current.latest != self.latest_release.tag:
            return False
        if asset not in compatible_assets(self.latest_release.assets):
            return False
        self.is_downloading = True
        self.last_download = None
        self.downloaded_bytes = self.total_bytes = 0
        self._cancel.clear()
        self.stateChanged.emit()

        def progress(downloaded: int, total: int):
            self.downloaded_bytes, self.total_bytes = downloaded, total
            self.downloadProgress.emit(downloaded, total)

        def run():
            try:
                path = download_asset(asset, destination, cancel=self._cancel, progress=progress)
                result = AppDownloadResult(success=True, message="更新包下载完成。", path=path)
            except DownloadCancelled as exc:
                result = AppDownloadResult(cancelled=True, message=str(exc))
            except Exception as exc:
                logger.warning("Software update download failed: %s", exc)
                result = AppDownloadResult(message=network_error(exc))
            self._downloadReady.emit(result)

        threading.Thread(target=run, name="F4CP-UpdateDownload", daemon=True).start()
        return True

    def cancel_download(self) -> None:
        self._cancel.set()

    def _finish_download(self, result: AppDownloadResult) -> None:
        self.is_downloading = False
        self.last_download = result.path if result.success else None
        self.stateChanged.emit()
        self.downloadFinished.emit(result)


update_manager = UpdateManager()
