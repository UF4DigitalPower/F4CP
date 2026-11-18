"""Shared Fluent page and card layouts."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import CardWidget, CaptionLabel, SubtitleLabel
from app.widgets.components import PageHeader


def section(parent, title, subtitle):
    card = CardWidget(parent)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)
    layout.addWidget(SubtitleLabel(title, card))
    caption = CaptionLabel(subtitle, card)
    caption.setWordWrap(True)
    caption.setVisible(bool(subtitle))
    layout.addWidget(caption)
    return card, layout


def page_content(page, name, title, subtitle):
    page.setObjectName(name)
    page.setWidgetResizable(True)
    page.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    content = QWidget()
    content.setObjectName(name + "Content")
    page.setWidget(content)
    page.setStyleSheet("QScrollArea, QWidget#" + name + "Content { background: transparent; border: none; }")
    layout = QVBoxLayout(content)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(12)
    layout.addWidget(PageHeader(title, subtitle, content))
    return content, layout


