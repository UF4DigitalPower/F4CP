# -*- coding: utf-8 -*-
# -------------------------------
#  @Project : F4CP
#  @Time    : 2026 - 01-08 12:30
#  @FileName: page_home.py
#  @FileType: 首页页面文件，负责应用概览、版本和入口卡片
#  @Software: PyCharm 2024.1.6 (Professional Edition)
#  @System  : Windows 11 23H2
#  @Author  : UF4
#  @Contact :
#  @Python  : 3.10
# -------------------------------

from PyQt5.QtCore import QSize, Qt, QUrl, QTimer
from PyQt5.QtGui import QColor, QDesktopServices, QFont, QImage
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    HeaderCardWidget,
    HorizontalFlipView,
    HyperlinkLabel,
    ImageLabel,
    PillPushButton,
    PrimaryPushButton,
    SimpleCardWidget,
    TransparentToolButton,
    setFont, ScrollArea,
)
from config import CTX, AppIconPath
from app.manager import StyleSheet, update_manager
from .page_layout import page_content, section
from app.widgets.components.software_update_card import SoftwareUpdateCard
from app.widgets.components.workspace_widgets import HeroBanner, ShortcutCard

class AppInfoCard(SimpleCardWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBorderRadius(16)
        self.iconLabel = ImageLabel(QImage(AppIconPath), self)
        self.iconLabel.setBorderRadius(8, 8, 8, 8)
        self.iconLabel.scaledToWidth(72)

        self.nameLabel = BodyLabel("F4CP 桌面客户端", self)
        setFont(self.nameLabel, 20, QFont.DemiBold)

        self.installButton = PrimaryPushButton(self)
        self.companyLabel = HyperlinkLabel(
            QUrl("https://github.com/UF4OVER"), "UF4OVER", self
        )
        self.installButton.setFixedWidth(160)

        self.descriptionLabel = BodyLabel(self)
        self.descriptionLabel.setWordWrap(True)

        self.tagButton1 = PillPushButton(self)
        self.tagButton1.setCheckable(False)
        setFont(self.tagButton1, 12)
        self.tagButton1.setFixedSize(80, 32)

        self.tagButton2 = PillPushButton(self)
        self.tagButton2.setCheckable(False)
        setFont(self.tagButton2, 12)
        self.tagButton2.setFixedSize(80, 32)

        self.shareButton = TransparentToolButton(FluentIcon.SHARE, self)
        self.shareButton.setFixedSize(32, 32)
        self.shareButton.setIconSize(QSize(15, 15))

        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.mainLayout.setSpacing(0)
        self.hBoxLayout = QHBoxLayout()
        self.mainLayout.addLayout(self.hBoxLayout)
        self.vBoxLayout = QVBoxLayout()
        self.topLayout = QHBoxLayout()
        self.buttonLayout = QHBoxLayout()

        self.initLayout()
        self.applyTexts()
        self.softwareUpdateCard = SoftwareUpdateCard(self, embedded=True)
        detailsLayout = QVBoxLayout()
        detailsLayout.setContentsMargins(24, 0, 24, 24)
        detailsLayout.addWidget(self.softwareUpdateCard)
        self.mainLayout.addLayout(detailsLayout)

    def initLayout(self):
        self.hBoxLayout.setSpacing(22)
        self.hBoxLayout.setContentsMargins(26, 24, 26, 20)
        self.hBoxLayout.addWidget(self.iconLabel, 0, Qt.AlignTop)
        self.hBoxLayout.addLayout(self.vBoxLayout, 1)

        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setSpacing(0)

        self.vBoxLayout.addLayout(self.topLayout)
        self.topLayout.setContentsMargins(0, 0, 0, 0)
        self.topLayout.addWidget(self.nameLabel)
        self.topLayout.addWidget(self.installButton, 0, Qt.AlignRight)

        self.vBoxLayout.addSpacing(3)
        self.vBoxLayout.addWidget(self.companyLabel)
        self.vBoxLayout.addSpacing(12)
        self.vBoxLayout.addWidget(self.descriptionLabel)

        self.vBoxLayout.addSpacing(12)
        self.buttonLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.addLayout(self.buttonLayout)
        self.buttonLayout.addWidget(self.tagButton1, 0, Qt.AlignLeft)
        self.buttonLayout.addWidget(self.tagButton2, 0, Qt.AlignLeft)

        self.buttonLayout.addWidget(self.shareButton, 1, Qt.AlignRight)

    def applyTexts(self):
        if not self.installButton.isEnabled():
            self.installButton.setText('检查中...')
        else:
            self.installButton.setText('检查更新')
        self.descriptionLabel.setText(
            "管理 UF4 设备的连接、固件与桌面软件版本。此处查看版本说明，检查并下载软件更新。"
        )
        self.tagButton1.setText('稳定版')
        self.tagButton2.setText('桌面上位机')
        self.tagButton2.setFixedWidth(108)
    def setCheckInProgress(self, checking: bool) -> None:
        self.installButton.setEnabled(not checking)
        self.applyTexts()


class GalleryCard(HeaderCardWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBorderRadius(16)
        self.flipView = HorizontalFlipView(self)
        self.expandButton = TransparentToolButton(FluentIcon.CHEVRON_RIGHT_MED, self)

        self.expandButton.setFixedSize(32, 32)
        self.expandButton.setIconSize(QSize(12, 12))

        imgPath = CTX.dirs.AssetsDir / "F4CP_2x1_1200x600.png"
        self.flipView.addImages([QImage(str(imgPath))])
        self.flipView.setBorderRadius(8)
        self.flipView.setSpacing(10)

        itemSize = QSize(620, 351)
        self.flipView.setItemSize(itemSize)
        self.flipView.setMinimumSize(itemSize)

        self.headerLayout.addWidget(self.expandButton, 0, Qt.AlignRight)
        self.viewLayout.addWidget(self.flipView)
        self.applyTexts()

    def applyTexts(self):
        self.setTitle('UF4 · 项目预览')


class HomePage(ScrollArea):
    """Application overview with integrated software updates and screenshot gallery."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HomePage")
        self.scrollWidget = QWidget(self)
        self.scrollWidget.setObjectName("homeScrollWidget")
        self.vBoxLayout = QVBoxLayout(self.scrollWidget)
        self.vBoxLayout.setContentsMargins(28, 24, 28, 28)
        self.vBoxLayout.setSpacing(18)
        self.hero = HeroBanner("UF4 数字电源工作台", "设备连接、固件烧录与版本管理，集中在一个工作空间。", self.scrollWidget)
        self.vBoxLayout.addWidget(self.hero)
        shortcuts = QHBoxLayout()
        shortcuts.setSpacing(14)
        self.firmwareShortcut = ShortcutCard(FluentIcon.DOWNLOAD, "固件下载", "V208 / G474 · 无线与有线", self.scrollWidget)
        self.settingsShortcut = ShortcutCard(FluentIcon.PALETTE, "个性化", "主题、颜色与全局字体", self.scrollWidget)
        self.projectShortcut = ShortcutCard(FluentIcon.CODE, "个人与项目", "作者、许可与项目信息", self.scrollWidget)
        for card in (self.firmwareShortcut, self.settingsShortcut, self.projectShortcut):
            shortcuts.addWidget(card, 1)
        self.firmwareShortcut.clicked.connect(lambda: self._open_page("firmwareInterface"))
        self.settingsShortcut.clicked.connect(lambda: self._open_page("settingInterface"))
        self.projectShortcut.clicked.connect(lambda: self._open_page("profileInterface"))
        self.vBoxLayout.addLayout(shortcuts)
        self.appCard = AppInfoCard(self.scrollWidget)
        self.softwareUpdateCard = self.appCard.softwareUpdateCard
        self.galleryCard = GalleryCard(self.scrollWidget)
        for card in (self.appCard, self.galleryCard):
            self.vBoxLayout.addWidget(card, 0, Qt.AlignTop)
        self.vBoxLayout.addStretch(1)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.appCard.installButton.clicked.connect(self.requestUpdateCheck)
        self.appCard.shareButton.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(CTX.cfg.appRepoUrl.value)))
        self.galleryCard.expandButton.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(CTX.dirs.AssetsDir / "F4CP_2x1_1200x600.png"))))
        CTX.versions.changed.connect(self._applyVersionSnapshot)
        update_manager.stateChanged.connect(self._syncUpdate)
        self._applyVersionSnapshot(CTX.versions.snapshot())
        self._syncUpdate()
        StyleSheet.HOME_PAGE.apply(self)
        CTX.cfg.themeChanged.connect(lambda *_: StyleSheet.HOME_PAGE.apply(self))
        self._startupTimer = QTimer(self)
        self._startupTimer.setSingleShot(True)
        self._startupTimer.timeout.connect(self._checkAtStartup)
        if CTX.cfg.checkUpdateAtStartUp.value:
            self._startupTimer.start(1000)

    def _applyVersionSnapshot(self, snapshot):
        self.appCard.tagButton1.setText(snapshot.app.current or "--")
        self.appCard.tagButton1.setFixedWidth(130)

    def _open_page(self, name):
        window = self.window()
        page = getattr(window, name, None)
        if page is not None and hasattr(window, "switchTo"):
            window.switchTo(page)
            window.navigationInterface.setCurrentItem(page.objectName())

    def requestUpdateCheck(self):
        self.softwareUpdateCard.checkForUpdates()

    def _checkAtStartup(self):
        self.softwareUpdateCard.checkForUpdates(manual=False)

    def _syncUpdate(self):
        checking, downloading = update_manager.is_checking, update_manager.is_downloading
        self.appCard.setCheckInProgress(checking or downloading)
        if downloading:
            self.appCard.installButton.setText("正在下载…")
        self.appCard.tagButton1.setText(CTX.versions.snapshot().app.current or "--")
