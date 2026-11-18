"""Shared Fluent page and card layouts."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CardWidget, CaptionLabel, StrongBodyLabel
from app.widgets.components import PageHeader
from app.widgets.components.workspace_widgets import IconTile


def section(parent, title, subtitle, *, icon=None, embedded=False):
    card = QWidget(parent) if embedded else CardWidget(parent)
    if not embedded:
        card.setBorderRadius(14)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(*((0, 0, 0, 0) if embedded else (22, 20, 22, 22)))
    layout.setSpacing(16)
    header = QHBoxLayout()
    header.setSpacing(12)
    if icon is not None:
        header.addWidget(IconTile(icon, card, 36))
    header.addWidget(StrongBodyLabel(title, card), 1)
    layout.addLayout(header)
    caption = CaptionLabel(subtitle, card)
    caption.setWordWrap(True)
    caption.setTextColor("#657085", "#a4aab7")
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
    layout.setContentsMargins(28, 24, 28, 28)
    layout.setSpacing(20)
    layout.addWidget(PageHeader(title, subtitle, content))
    return content, layout


