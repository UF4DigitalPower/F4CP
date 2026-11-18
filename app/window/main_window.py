# -*- coding: utf-8 -*-
from __future__ import annotations

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QWidget
from qfluentwidgets import FluentIcon as FIF, MSFluentWindow, PushButton

from app.widgets.components import DynamicIsland

from .navigation import NavigationMixin
from .shell import WindowShellMixin
from .theme import ThemeBackgroundMixin


class Window(WindowShellMixin, NavigationMixin, ThemeBackgroundMixin, MSFluentWindow):
    """Main application window, composed from focused window concerns."""

    def __init__(self):
        from config import cfg
        from qfluentwidgets import setTheme
        setTheme(cfg.themeMode.value, save=False)
        super().__init__()
        self.setObjectName("Window")
        self.initWindowShell()
        QApplication.processEvents()

        self.createPages()
        self.registerNavigation()

        self.titleBar.raise_()
        self.titleBar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        titleLayout = self.titleBar.hBoxLayout
        self.notificationArea = QWidget(self.titleBar)
        spacerIndex = titleLayout.count() - 2
        titleLayout.takeAt(spacerIndex)
        titleLayout.insertWidget(spacerIndex, self.notificationArea, 1)
        notificationLayout = QHBoxLayout(self.notificationArea)
        notificationLayout.setContentsMargins(12, 0, 12, 0)
        notificationLayout.addStretch()
        self.dynamicIsland = DynamicIsland(self.notificationArea)
        notificationLayout.addWidget(self.dynamicIsland, 0, Qt.AlignVCenter)
        notificationLayout.addStretch()
        self.dynamicIsland.raise_()

        self.logButton = PushButton(FIF.DOCUMENT, "运行日志", self.titleBar)
        self.logButton.setFixedHeight(32)
        self.logButton.clicked.connect(self.firmwareInterface.logDialog.open_log)
        titleLayout.insertWidget(titleLayout.count() - 1, self.logButton, 0, Qt.AlignVCenter)
        titleLayout.insertSpacing(titleLayout.count() - 1, 12)

        self.initThemeBackground()

    def showDynamicIsland(self, title: str, content: str = "", level: str = "info", duration: int = 3200):
        self.dynamicIsland.notify(title, content, level, duration)

    def closeEvent(self, event):
        from PyQt5.QtWidgets import QMessageBox
        if self.firmwareInterface._active:
            if not self.firmwareInterface._can_cancel:
                QMessageBox.information(self, "正在下载固件", "请等待固件烧录、校验及安装确认完成后退出。")
                event.ignore()
                return
            if QMessageBox.question(self, "退出 F4CP", "退出会取消当前固件上传，是否继续？") != QMessageBox.Yes:
                event.ignore()
                return
            # Cancel cooperatively: a queued phase signal may lag behind the
            # worker entering its non-cancellable commit/programming phase.
            self.firmwareInterface._cancel()
            event.ignore()
            return
        if not self.firmwareInterface.shutdown():
            event.ignore()
            return
        super().closeEvent(event)
