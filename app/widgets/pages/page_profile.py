"""Application identity, project links and supplied copyright registration details."""
import json

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, FluentIcon as FIF, HyperlinkLabel,
                            ScrollArea, SimpleCardWidget, TitleLabel)

from app.widgets.components.profile_info_card import ProfileInfoCard
from .page_layout import page_content
from config import AUTHOR, AppIconPath, CTX, REPO_URL


def detail_rows(parent, body, rows):
    """Keep field names aligned and values selectable, with wrapping for long text."""
    grid = QGridLayout()
    grid.setHorizontalSpacing(18)
    grid.setVerticalSpacing(12)
    grid.setColumnStretch(1, 1)
    for index, (name, value) in enumerate(rows):
        key = CaptionLabel(name, parent)
        key.setTextColor("#657085", "#a4aab7")
        grid.addWidget(key, index, 0, Qt.AlignTop)
        label = value if isinstance(value, QWidget) else BodyLabel(value, parent)
        if isinstance(label, QLabel):
            label.setWordWrap(True)
            label.setTextFormat(Qt.PlainText)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(label, index, 1, Qt.AlignTop)
        else:
            grid.addWidget(label, index, 1, Qt.AlignTop | Qt.AlignLeft)
    body.addLayout(grid)


class ProfilePage(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        widget, layout = page_content(self, "ProfilePage", "应用信息", "应用版本、源码仓库与软件著作权登记信息。")

        self.identityCard = SimpleCardWidget(widget)
        self.identityCard.setBorderRadius(16)
        identity = QVBoxLayout(self.identityCard)
        identity.setContentsMargins(24, 20, 24, 20)
        identity.setSpacing(6)
        self.iconLabel = QLabel(self.identityCard)
        self.iconLabel.setFixedSize(72, 72)
        self.iconLabel.setPixmap(QIcon(AppIconPath).pixmap(72, 72))
        self.iconLabel.setAlignment(Qt.AlignCenter)
        identity.addWidget(self.iconLabel, 0, Qt.AlignHCenter)
        identity.addWidget(TitleLabel("F4CP", self.identityCard), 0, Qt.AlignHCenter)
        self.softwareNameLabel = BodyLabel(self.identityCard)
        self.softwareNameLabel.setAlignment(Qt.AlignCenter)
        self.softwareNameLabel.setWordWrap(True)
        identity.addWidget(self.softwareNameLabel)
        maintainer = CaptionLabel(f"UF4 Digital Power  ·  维护者 {AUTHOR}", self.identityCard)
        maintainer.setAlignment(Qt.AlignCenter)
        maintainer.setTextColor("#657085", "#a4aab7")
        identity.addWidget(maintainer)
        layout.addWidget(self.identityCard)

        self.projectCard = card = ProfileInfoCard(FIF.INFO, "项目详情", "应用版本与开发框架", widget)
        body = card.bodyLayout
        self.versionLabel = BodyLabel(card)
        detail_rows(card, body, (("应用名称", "F4CP"), ("当前版本", self.versionLabel),
                                 ("开发框架", "Python · PyQt5\nQFluentWidgets")))
        layout.addWidget(card)

        self.repositoryCard = card = ProfileInfoCard(FIF.CODE, "源码仓库", "开源许可、项目地址与联系邮箱", widget)
        body = card.bodyLayout
        self.repositoryLink = HyperlinkLabel(QUrl(REPO_URL), REPO_URL.removeprefix("https://"), card)
        email = HyperlinkLabel(QUrl("mailto:heping@hepi.ng"), "heping@hepi.ng", card)
        detail_rows(card, body, (("开源协议", "GPL-3.0-only"), ("主仓库", self.repositoryLink), ("联系邮箱", email)))
        layout.addWidget(card)

        self.copyrightCard = ProfileInfoCard(FIF.DOCUMENT, "知识产权", "计算机软件著作权登记", widget)
        body = self.copyrightCard.bodyLayout
        self.copyrightFields = {}
        fields = (("SoftwareName", "登记软件"), ("CertificateNumber", "证书号"),
                  ("RegistrationNumber", "登记号"), ("Owner", "著作权人"),
                  ("AcquisitionMethod", "权利取得方式"), ("RightsScope", "权利范围"),
                  ("RegistrationDate", "登记日期"))
        rows = []
        for key, name in fields:
            value = BodyLabel(self.copyrightCard)
            self.copyrightFields[key] = value
            rows.append((name, value))
        detail_rows(self.copyrightCard, body, rows)
        layout.addWidget(self.copyrightCard)
        layout.addStretch()
        CTX.versions.changed.connect(self._refresh)
        self._refresh()
        for card in (self.projectCard, self.repositoryCard, self.copyrightCard):
            card.setExpand(True)

    def _refresh(self, *_):
        try:
            metadata = json.loads((CTX.dirs.ConfigDir / "profile.json").read_text(encoding="utf-8-sig"))
            if not isinstance(metadata, dict):
                metadata = {}
        except (OSError, ValueError):
            metadata = {}
        for key, label in self.copyrightFields.items():
            value = metadata.get(key)
            text = value.strip() if isinstance(value, str) else ""
            label.setText(text or ("F4CP 数字电源管理软件" if key == "SoftwareName" else "待补充"))
        self.softwareNameLabel.setText(self.copyrightFields["SoftwareName"].text())
        version = CTX.versions.snapshot().app.current or "--"
        self.versionLabel.setText(version)
        for card in (self.projectCard, self.repositoryCard, self.copyrightCard):
            card.refreshContent()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh()
