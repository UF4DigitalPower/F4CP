import json
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from qfluentwidgets import BodyLabel, PushButton, ScrollArea
from .page_home import section, page_content
from config import AUTHOR, REPO_URL, CTX


class ProfilePage(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        widget, layout = page_content(self, "ProfilePage", "个人与项目", "作者、项目介绍与软件著作权信息。")
        card, body = section(widget, AUTHOR, "UF4 Digital Power · F4CP")
        intro = BodyLabel("F4CP 是 UF4 数字电源的桌面工具，提供设备连接、通信调试、固件 OTA 与软件更新。\n联系邮箱：heping@hepi.ng", card)
        intro.setWordWrap(True)
        body.addWidget(intro)
        button = PushButton("访问项目仓库", card)
        button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REPO_URL)))
        body.addWidget(button, 0, Qt.AlignLeft)
        layout.addWidget(card)
        card, body = section(widget, "软件著作权", "作品与登记信息")
        self.copyrightLabel = BodyLabel(card)
        self.copyrightLabel.setWordWrap(True)
        self.copyrightLabel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.addWidget(self.copyrightLabel)
        layout.addWidget(card)
        card, body = section(widget, "开源许可", "F4CP · GPL-3.0-only")
        label = BodyLabel("软件使用、修改和分发遵循随附 LICENSE。芯片厂商 SDK 与 BLE 库保留各自许可和使用条件。", card)
        label.setWordWrap(True)
        body.addWidget(label)
        layout.addWidget(card)
        layout.addStretch()
        self._refresh()

    def _refresh(self):
        try:
            metadata = json.loads((CTX.dirs.ConfigDir / "profile.json").read_text(encoding="utf-8-sig"))
            if not isinstance(metadata, dict):
                metadata = {}
        except (OSError, ValueError):
            metadata = {}
        self.copyrightLabel.setText(
            f"软件名称：{metadata.get('SoftwareName') or 'F4CP 数字电源管理软件'}\n"
            f"著作权人：{metadata.get('Owner') or '待补充'}\n"
            f"登记号：{metadata.get('RegistrationNumber') or '待补充'}\n"
            f"登记日期：{metadata.get('RegistrationDate') or '待补充'}")

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh()
