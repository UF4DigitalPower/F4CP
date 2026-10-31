"""Shared software Release controls for the version page and home update prompt."""
from __future__ import annotations

import platform
from pathlib import Path

from PyQt5.QtCore import QStandardPaths, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout
from qfluentwidgets import (
    CaptionLabel, CardWidget, ComboBox, FluentIcon as FIF, PrimaryPushButton,
    ProgressBar, PushButton, StrongBodyLabel, TextEdit,
)

from app.core.github_release import ReleaseError, compatible_assets, is_newer_version, validate_asset_name
from app.core.utility import showMessage
from app.manager.manager_update import update_manager


class SoftwareUpdateCard(CardWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._hasUpdate = False
        self._assets = []
        self._manualCheck = False
        self._downloadRequested = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(10)
        layout.addWidget(StrongBodyLabel("软件更新 · GitHub Release", self))
        self.versionLabel = CaptionLabel(self)
        self.versionLabel.setWordWrap(True)
        layout.addWidget(self.versionLabel)

        row = QHBoxLayout()
        self.checkButton = PushButton(FIF.SYNC, "检查软件更新", self)
        self.releaseButton = PushButton(FIF.LINK, "打开发布页", self)
        self.releaseButton.clicked.connect(self._openRelease)
        self.checkButton.clicked.connect(lambda: self.checkForUpdates())
        row.addWidget(self.checkButton)
        row.addWidget(self.releaseButton)
        row.addStretch(1)
        layout.addLayout(row)

        self.notesEdit = TextEdit(self)
        self.notesEdit.setReadOnly(True)
        self.notesEdit.setPlaceholderText("检查更新后显示 Release 更新说明。")
        self.notesEdit.setFixedHeight(150)
        layout.addWidget(self.notesEdit)

        downloadRow = QHBoxLayout()
        self.assetCombo = ComboBox(self)
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
        layout.addLayout(downloadRow)

        self.progressBar = ProgressBar(self)
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)
        self.progressBar.hide()
        layout.addWidget(self.progressBar)
        self.statusLabel = CaptionLabel("点击检查更新，将按当前系统和架构匹配发布文件。", self)
        self.statusLabel.setWordWrap(True)
        layout.addWidget(self.statusLabel)

        update_manager.checkFinished.connect(self._onCheckFinished)
        update_manager.downloadProgress.connect(self._onProgress)
        update_manager.downloadFinished.connect(self._onDownloadFinished)
        update_manager.stateChanged.connect(self._syncState)
        self._syncState()

    def checkForUpdates(self, manual: bool = True) -> None:
        if update_manager.check_for_updates(manual=manual):
            self._manualCheck = manual
            self._hasUpdate = False
            self._assets = []
            self.assetCombo.clear()
            self.notesEdit.clear()
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
            self.notesEdit.clear()
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
        self.notesEdit.setPlainText(result.release_notes or "该版本未填写更新内容。")
        if self._hasUpdate:
            message = f"发现新版本 {result.release_tag}。请选择保存位置下载更新包。"
        elif is_newer_version(result.snapshot.local_app_version, result.release_tag):
            message = "当前运行版本高于最新 Release，无需降级。"
        else:
            message = "当前已是最新软件版本。"
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

    def _syncState(self) -> None:
        checking, downloading = update_manager.is_checking, update_manager.is_downloading
        snapshot = update_manager.get_cached_versions()
        channel = "包含预发布" if update_manager.context.cfg.includePrereleases.value else "正式发布"
        self.versionLabel.setText(f"当前：{snapshot.local_app_version}  |  最新发布：{snapshot.latest_app_version or '--'}  |  {platform.system()} / {platform.machine()}  |  {channel}")
        self.checkButton.setEnabled(not checking and not downloading)
        self.checkButton.setText("检查中…" if checking else "检查软件更新")
        self.assetCombo.setEnabled(not checking and not downloading and bool(self._assets))
        self.downloadButton.setEnabled(not checking and not downloading and self._hasUpdate and bool(self._assets))
        self.cancelButton.setVisible(downloading)
        self.cancelButton.setEnabled(downloading)
        self.openFolderButton.setVisible(update_manager.last_download is not None)
        self.releaseButton.setEnabled(not checking)

    def _openRelease(self) -> None:
        release = update_manager.latest_release
        url = release.url if release else update_manager.context.cfg.appReleaseUrl.value
        QDesktopServices.openUrl(QUrl(url))

    def _openDownloadFolder(self) -> None:
        if update_manager.last_download:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(update_manager.last_download.parent)))
