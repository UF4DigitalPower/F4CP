"""Qt bridge for GitHub software updates; network and disk I/O run off the GUI thread."""
from __future__ import annotations

import threading
import weakref
from dataclasses import dataclass, field
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
    is_newer_version,
    network_error,
)
from config import CTX, get_logger

logger = get_logger("SoftwareUpdate")


@dataclass(frozen=True)
class VersionSnapshot:
    local_app_version: str = ""
    latest_app_version: str = ""
    local_lower_version: str = ""
    latest_lower_version: str = ""
    local_upper_version: str = ""
    latest_upper_version: str = ""


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
    _checkReady = pyqtSignal(object)
    _downloadReady = pyqtSignal(object)

    def __init__(self, context=CTX):
        super().__init__()
        self.context = context
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
        cfg = self.context.cfg
        return VersionSnapshot(
            local_app_version=cfg.appVersion.value,
            latest_app_version=cfg.latestAppVersion.value,
            local_lower_version=cfg.localLowerVersion.value,
            latest_lower_version=cfg.latestLowerVersion.value,
            local_upper_version=cfg.localUpperVersion.value,
            latest_upper_version=cfg.latestUpperVersion.value,
        )

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
                result = UpdateCheckResult(
                    success=True, manual=manual,
                    has_changes=is_newer_version(release.tag, snapshot.local_app_version),
                    snapshot=VersionSnapshot(
                        local_app_version=snapshot.local_app_version, latest_app_version=release.tag,
                        local_lower_version=snapshot.local_lower_version, latest_lower_version=snapshot.latest_lower_version,
                        local_upper_version=snapshot.local_upper_version, latest_upper_version=snapshot.latest_upper_version,
                    ),
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
            cfg = self.context.cfg
            try:
                cfg.set(cfg.latestAppVersion, result.release_tag, save=True)
            except OSError as exc:
                logger.warning("Could not save latest software version: %s", exc)
        target = self._check_target() if self._check_target else None
        self._check_target = None
        self.stateChanged.emit()
        self.checkFinished.emit(result)
        if target is not None and not sip.isdeleted(target):
            QCoreApplication.postEvent(target, UpdateCheckFinishedEvent(result))

    def download_update(self, asset: ReleaseAsset, destination: Path) -> bool:
        if self.is_downloading or self.is_checking or self.latest_release is None:
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
