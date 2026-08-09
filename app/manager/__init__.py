# -*- coding: utf-8 -*-
# -------------------------------
#  @Project : F4CP
#  @Time    : 2026 - 01-08 12:30
#  @FileName: __init__.py
#  @FileType: 包初始化文件，整理模块对外导出入口
#  @Software: PyCharm 2024.1.6 (Professional Edition)
#  @System  : Windows 11 23H2
#  @Author  : UF4
#  @Contact :
#  @Python  : 3.10
# -------------------------------

from __future__ import annotations

from dataclasses import dataclass, field

from PyQt5.QtCore import QEvent, QThread, pyqtSignal

from .manager_font import *
from .manager_stylesheet import *


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
    message: str = "更新逻辑已移除。"
    snapshot: VersionSnapshot = field(default_factory=VersionSnapshot)
    release_tag: str = ""


@dataclass(frozen=True)
class FirmwareRelease:
    kind: str = ""
    version: str = ""
    date: str = ""
    channel: str = ""
    device: str = ""
    hardware: str = ""
    size: int = 0
    asset_name: str = ""
    sha256: str = ""


@dataclass(frozen=True)
class FirmwareCheckResult:
    success: bool = False
    message: str = "固件更新逻辑已移除。"
    latest: dict[str, FirmwareRelease | None] = field(default_factory=dict)
    has_updates: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class FirmwareDownloadResult:
    success: bool = False
    kind: str = ""
    message: str = "固件下载逻辑已移除。"
    release: FirmwareRelease | None = None


@dataclass(frozen=True)
class FirmwareHistoryResult:
    success: bool = False
    message: str = "固件历史逻辑已移除。"
    releases: dict[str, list[FirmwareRelease]] = field(default_factory=lambda: {"Power": [], "Upper": []})


@dataclass(frozen=True)
class FirmwareDetailResult:
    success: bool = False
    message: str = "固件详情逻辑已移除。"
    release: FirmwareRelease | None = None
    changelog: str = ""


@dataclass(frozen=True)
class GithubSessionState:
    authenticated: bool = False
    display_name: str = ""
    github_login: str = ""
    expires_at: int = 0
    session_token: str = ""


@dataclass(frozen=True)
class GithubAuthResult:
    success: bool = False
    message: str = "GitHub 逻辑已移除。"
    session: GithubSessionState | None = None


class _ResultEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, result):
        super().__init__(self.EVENT_TYPE)
        self.result = result


class UpdateCheckFinishedEvent(_ResultEvent):
    pass


class FirmwareCheckFinishedEvent(_ResultEvent):
    pass


class FirmwareDownloadFinishedEvent(_ResultEvent):
    pass


class FirmwareHistoryFinishedEvent(_ResultEvent):
    pass


class FirmwareDetailFinishedEvent(_ResultEvent):
    pass


class _DisabledUpdateManager:
    is_checking = False

    def get_cached_versions(self) -> VersionSnapshot:
        return VersionSnapshot()

    def check_for_updates(self, parent=None, manual: bool = True) -> bool:
        return False


class _DisabledFirmwareCheckManager:
    is_checking = False

    def check_updates(self, parent=None) -> bool:
        return False


class _DisabledFirmwareDownloadManager:
    def is_downloading(self, kind: str) -> bool:
        return False

    def download_latest(self, kind: str, parent=None) -> bool:
        return False

    def download_release(self, release: FirmwareRelease, parent=None) -> bool:
        return False


class _DisabledFirmwareHistoryManager:
    is_refreshing = False

    def cached_history(self) -> dict[str, list[FirmwareRelease]]:
        return {"Power": [], "Upper": []}

    def cached_detail(self, kind: str, version: str):
        return None

    def refresh_history(self, parent=None, force_refresh: bool = False) -> bool:
        return False

    def load_detail(self, kind: str, version: str, parent=None) -> bool:
        return False


class _DisabledFirmwareManager:
    def GetLowerFirmware(self):
        return []

    def GetUpperFirmware(self):
        return []


class _DisabledGithubThread(QThread):
    authorizeUrlReady = pyqtSignal(str)
    resultReady = pyqtSignal(object)

    def __init__(self, *args, **kwargs):
        parent = kwargs.get("parent")
        if parent is None and args and hasattr(args[-1], "QObject"):
            parent = args[-1]
        super().__init__(parent)

    def start(self):
        self.resultReady.emit(GithubAuthResult())
        self.finished.emit()


GithubLoginThread = _DisabledGithubThread
GithubLogoutThread = _DisabledGithubThread
GithubSessionRefreshThread = _DisabledGithubThread

update_manager = _DisabledUpdateManager()
firmware_check_manager = _DisabledFirmwareCheckManager()
firmware_download_manager = _DisabledFirmwareDownloadManager()
firmware_history_manager = _DisabledFirmwareHistoryManager()
firmware_manager = _DisabledFirmwareManager()


def cached_session_state() -> GithubSessionState:
    return GithubSessionState()
