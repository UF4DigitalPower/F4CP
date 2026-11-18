from PyQt5.QtCore import QTimer
from qfluentwidgets import ScrollArea
from app.widgets.components.software_update_card import SoftwareUpdateCard
from .page_home import page_content
from config import cfg


class VersionPage(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        widget, layout = page_content(self, "VersionPage", "软件更新", "检查 F4CP 新版本并下载更新包。")
        self.softwareUpdateCard = SoftwareUpdateCard(widget)
        layout.addWidget(self.softwareUpdateCard)
        layout.addStretch()
        if cfg.checkUpdateAtStartUp.value:
            QTimer.singleShot(1000, lambda: self.softwareUpdateCard.checkForUpdates(manual=False))
