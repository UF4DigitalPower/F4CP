# -*- coding: utf-8 -*-
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, TitleLabel


class PageHeader(QWidget):
    """Consistent page header used by all top-level pages."""

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("PageHeader")

        self.titleLabel = TitleLabel(title, self)
        self.subtitleLabel = CaptionLabel(subtitle, self)
        self.subtitleLabel.setWordWrap(True)
        self.subtitleLabel.setVisible(bool(subtitle))

        self._textLayout = QVBoxLayout()
        self._textLayout.setContentsMargins(0, 0, 0, 0)
        self._textLayout.setSpacing(2)
        self._textLayout.addWidget(self.titleLabel)
        self._textLayout.addWidget(self.subtitleLabel)

        self.actionBox = QWidget(self)
        self.actionLayout = QHBoxLayout(self.actionBox)
        self.actionLayout.setContentsMargins(0, 0, 0, 0)
        self.actionLayout.setSpacing(10)

        self.mainLayout = QHBoxLayout(self)
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.mainLayout.setSpacing(16)
        self.mainLayout.addLayout(self._textLayout, 1)
        self.mainLayout.addWidget(self.actionBox, 0, Qt.AlignTop)

        self.setMinimumHeight(54)

    def addAction(self, widget: QWidget) -> None:
        self.actionLayout.addWidget(widget)

    def addActions(self, widgets: list[QWidget] | tuple[QWidget, ...]) -> None:
        for widget in widgets:
            self.addAction(widget)
