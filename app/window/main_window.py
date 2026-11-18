# -*- coding: utf-8 -*-
from __future__ import annotations

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import QApplication
from qfluentwidgets import MSFluentWindow

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

        self.dynamicIsland = DynamicIsland(self.titleBar)
        self.dynamicIsland.recenter()
        self.dynamicIsland.raise_()

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
        if not self.homeInterface.shutdown():
            event.ignore()
            return
        super().closeEvent(event)
