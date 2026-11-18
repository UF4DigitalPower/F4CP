# -*- coding: utf-8 -*-
# -------------------------------
#  @Project : F4CP
#  @Time    : 2026 - 10-31
#  @FileName: software_update_card.py
#  @FileType: 软件更新卡片，展示统一版本状态并提供更新包下载入口
#  @Software: PyCharm 2024.1.6 (Professional Edition)
#  @System  : Windows 11 23H2
#  @Author  : UF4
#  @Contact :
#  @Python  : 3.11
# -------------------------------

"""Software Release notes and downloads, embedded in the home application card."""
from __future__ import annotations

import platform
from pathlib import Path

from PyQt5.QtCore import QStandardPaths, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel, CardWidget, ComboBox, FluentIcon as FIF, PrimaryPushButton,
    ProgressBar, PushButton, StrongBodyLabel, TextEdit, setCustomStyleSheet,
)

from app.core.github_release import ReleaseError, compatible_assets, validate_asset_name
from app.core.utility import showMessage
from app.manager.manager_update import update_manager
from app.version import parse_version, VersionError


class SoftwareUpdateCard(CardWidget):
    def __init__(self, parent=None, *, embedded=False):
        super().__init__(parent)
        self._hasUpdate = False
        self._assets = []
        self._manualCheck = False
        self._downloadRequested = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(10)
        header = QHBoxLayout()
        self.notesTitleLabel = StrongBodyLabel(self)
        header.addWidget(self.notesTitleLabel)
        header.addStretch(1)
        self.releaseButton = PushButton(FIF.LINK, "查看发布页", self)
        self.releaseButton.clicked.connect(self._openRelease)
        header.addWidget(self.releaseButton)
        layout.addLayout(header)
        self.versionLabel = CaptionLabel(self)
        self.versionLabel.setWordWrap(True)
        layout.addWidget(self.versionLabel)

        row = QHBoxLayout()
        self.checkButton = PushButton(FIF.SYNC, "检查软件更新", self)
        self.checkButton.clicked.connect(lambda: self.checkForUpdates())
        row.addWidget(self.checkButton)
        row.addStretch(1)
        if embedded:
            self.checkButton.hide()
        else:
            layout.addLayout(row)

        self.notesEdit = TextEdit(self)
        self.notesEdit.setObjectName("releaseNotes")
        self.notesEdit.setReadOnly(True)
        self.notesEdit.setFixedHeight(155)
        self.notesEdit.layer.hide()
        selector = "TextEdit#releaseNotes, TextEdit#releaseNotes:hover, TextEdit#releaseNotes:focus"
        setCustomStyleSheet(self.notesEdit,
                            selector + " { color: #202020; background: transparent; border: none; }",
                            selector + " { color: #f2f2f2; background: transparent; border: none; }")
        layout.addWidget(self.notesEdit)

        self.downloadPanel = QWidget(self)
        downloadRow = QHBoxLayout(self.downloadPanel)
        downloadRow.setContentsMargins(0, 0, 0, 0)
        self.assetCombo = ComboBox(self.downloadPanel)
        self.assetCombo.setMinimumWidth(240)
        self.downloadButton = PrimaryPushButton(FIF.DOWNLOAD, "下载更新包", self)
        self.cancelButton = PushButton(FIF.CLOSE, "取消下载", self)
        self.openFolderButton = PushButton(FIF.FOLDER, "打开下载目录", self)
        self.downloadButton.clicked.connect(self.downloadUpdate)
        self.cancelButton.clicked.connect(self._cancelDownload)
        self.openFolderButton.clicked.connect(self._openDownloadFolder)
        downloadRow.addWidget(self.assetCombo, 1)
        downloadRow.addWidget(self.downloadButton)
        downloadRow.addWidget(self.cancelButton)
        downloadRow.addWidget(self.openFolderButton)
        layout.addWidget(self.downloadPanel)

        self.progressBar = ProgressBar(self)
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)
        self.progressBar.hide()
        layout.addWidget(self.progressBar)
        self.statusLabel = CaptionLabel("点击上方“检查更新”获取新版本。" if embedded else "点击检查更新获取新版本。", self)
        self.statusLabel.setWordWrap(True)
        layout.addWidget(self.statusLabel)

        update_manager.checkFinished.connect(self._onCheckFinished)
        update_manager.downloadProgress.connect(self._onProgress)
        update_manager.downloadFinished.connect(self._onDownloadFinished)
        update_manager.stateChanged.connect(self._syncState)
        update_manager.versionsChanged.connect(self._onVersionsChanged)
        self._showReleaseNotes()
        self._syncState()

    def _showReleaseNotes(self, release=None, snapshot=None) -> None:
        snapshot = snapshot or update_manager.get_cached_versions()
        current = snapshot.app.current or "--"
        try:
            comparison = (parse_version(release.tag) > parse_version(current)) if release else False
            same_version = release is not None and parse_version(release.tag) == parse_version(current)
        except VersionError:
            comparison = same_version = False
        if comparison or (same_version and release.notes):
            self.notesTitleLabel.setText(f"{'新版本介绍' if comparison else '此版本介绍'} · {release.tag}")
            notes = release.notes or "此版本尚未提供更新说明，可前往发布页查看。"
        else:
            self.notesTitleLabel.setText(f"此版本介绍 · {current}")
            path = update_manager.context.dirs.AssetsDir / "f4cp-release-notes.md"
            try:
                notes = path.read_text(encoding="utf-8")
            except OSError:
                notes = "此版本未附带介绍。检查更新后可查看发布说明。"
        self.notesEdit.setMarkdown(notes)
        self.notesEdit.moveCursor(self.notesEdit.textCursor().Start)

    def checkForUpdates(self, manual: bool = True) -> None:
        if update_manager.check_for_updates(manual=manual):
            self._manualCheck = manual
            self._hasUpdate = False
            self._assets = []
            self.assetCombo.clear()
            self.progressBar.hide()
            self.statusLabel.setText("正在连接 GitHub，读取最新 Release…")
            self._syncState()
        elif manual:
            showMessage(self, "更新任务进行中", "请等待当前检查或下载完成。", "info")

    def _onCheckFinished(self, result) -> None:
        if not result.success:
            self._hasUpdate = False
            self._assets = []
            self.assetCombo.clear()
            self._showReleaseNotes()
            self.statusLabel.setText(result.message)
            if self._manualCheck:
                showMessage(self, "检查更新失败", result.message, "warning")
            self._manualCheck = False
            self._syncState()
            return
        self._hasUpdate = result.has_changes
        self._assets = compatible_assets(result.release.assets)
        self.assetCombo.clear()
        for asset in self._assets:
            self.assetCombo.addItem(f"{asset.name}  ({asset.size / 1024 / 1024:.1f} MiB)")
        self._showReleaseNotes(result.release, result.snapshot)
        message = result.snapshot.app.message
        if self._hasUpdate:
            message += "请选择保存位置下载更新包。"
        if not self._assets:
            message += f" 此 Release 没有适用于 {platform.system()} / {platform.machine()} 的附件，可打开发布页查看。"
        self.statusLabel.setText(message)
        self._manualCheck = False
        self._syncState()

    def downloadUpdate(self) -> None:
        index = self.assetCombo.currentIndex()
        if not self._hasUpdate or not 0 <= index < len(self._assets):
            return
        asset = self._assets[index]
        try:
            validate_asset_name(asset.name)
        except ReleaseError as exc:
            showMessage(self, "下载失败", str(exc), "warning")
            return
        directory = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or str(Path.home())
        filename, _ = QFileDialog.getSaveFileName(self, "保存 F4CP 更新包", str(Path(directory) / asset.name), "所有文件 (*)")
        if not filename:
            return
        if update_manager.download_update(asset, Path(filename)):
            self._downloadRequested = True
            self.progressBar.setRange(0, 100)
            self.progressBar.setValue(0)
            self.progressBar.show()
            self.statusLabel.setText(f"正在下载 {asset.name}…")
        else:
            showMessage(self, "下载未开始", "更新任务正在进行或 Release 已更改，请重新检查。", "warning")

    def _cancelDownload(self) -> None:
        update_manager.cancel_download()
        self.cancelButton.setEnabled(False)
        self.statusLabel.setText("正在取消下载…")

    def _onProgress(self, downloaded: int, total: int) -> None:
        self.progressBar.show()
        if total:
            self.progressBar.setRange(0, 100)
            self.progressBar.setValue(min(100, downloaded * 100 // total))
            self.statusLabel.setText(f"下载中：{downloaded / 1024 / 1024:.1f} / {total / 1024 / 1024:.1f} MiB")
        else:
            self.progressBar.setRange(0, 0)
            self.statusLabel.setText(f"已下载 {downloaded / 1024 / 1024:.1f} MiB")

    def _onDownloadFinished(self, result) -> None:
        if result.success:
            self.progressBar.setRange(0, 100)
            self.progressBar.setValue(100)
            self.statusLabel.setText(f"更新包已保存：{result.path}\n请退出当前程序后，手动解压或运行安装包。")
        else:
            self.progressBar.hide()
            self.statusLabel.setText(result.message)
        if self._downloadRequested:
            showMessage(self, "下载完成" if result.success else "下载已取消" if result.cancelled else "下载失败",
                        result.message, "success" if result.success else "info" if result.cancelled else "warning")
        self._downloadRequested = False
        self._syncState()

    def _onVersionsChanged(self, snapshot) -> None:
        release = update_manager.latest_release
        self._hasUpdate = snapshot.app.has_update and release is not None and release.tag == snapshot.app.latest
        self._syncState()

    def _syncState(self) -> None:
        checking, downloading = update_manager.is_checking, update_manager.is_downloading
        snapshot = update_manager.get_cached_versions()
        channel = "包含预发布" if update_manager.context.cfg.includePrereleases.value else "正式发布"
        self.versionLabel.setText(f"当前版本 {snapshot.app.current or '--'}  ·  最新发布 {snapshot.app.latest or '--'}  ·  {channel}")
        self.checkButton.setEnabled(not checking and not downloading)
        self.checkButton.setText("检查中…" if checking else "检查软件更新")
        self.assetCombo.setEnabled(not checking and not downloading and bool(self._assets))
        self.downloadButton.setEnabled(not checking and not downloading and self._hasUpdate and bool(self._assets))
        self.cancelButton.setVisible(downloading)
        self.cancelButton.setEnabled(downloading)
        self.openFolderButton.setVisible(update_manager.last_download is not None)
        self.downloadPanel.setVisible((self._hasUpdate and bool(self._assets)) or downloading or update_manager.last_download is not None)
        self.assetCombo.setVisible(self._hasUpdate and bool(self._assets))
        self.downloadButton.setVisible(self._hasUpdate and bool(self._assets))
        self.releaseButton.setEnabled(not checking)

    def _openRelease(self) -> None:
        release = update_manager.latest_release
        url = release.url if release else update_manager.context.cfg.appReleaseUrl.value
        QDesktopServices.openUrl(QUrl(url))

    def _openDownloadFolder(self) -> None:
        if update_manager.last_download:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(update_manager.last_download.parent)))
