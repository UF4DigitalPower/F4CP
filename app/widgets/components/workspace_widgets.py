"""Native Qt workspace surfaces; no dependency on the Pro component package."""
from pathlib import Path

from PyQt5.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QBoxLayout, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, FluentIcon as FIF, IconWidget,
                            SimpleCardWidget, StrongBodyLabel, TitleLabel, isDarkTheme, setFont)


class IconTile(QWidget):
    def __init__(self, icon, parent=None, size=40):
        super().__init__(parent)
        self.setFixedSize(size, size)
        layout = QVBoxLayout(self)
        margin = max(8, size // 4)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.addWidget(IconWidget(icon, self))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(245, 109, 91, 28 if isDarkTheme() else 20))
        painter.drawRoundedRect(self.rect(), 11, 11)


class HeroBanner(QWidget):
    def __init__(self, title, subtitle, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(180)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)
        eyebrow = CaptionLabel("UF4 DIGITAL POWER  /  F4CP", self)
        eyebrow.setTextColor(QColor("#ffd2bf"), QColor("#ffd2bf"))
        self.titleLabel = TitleLabel(title, self)
        self.titleLabel.setTextColor(QColor("#ffffff"), QColor("#ffffff"))
        self.subtitleLabel = BodyLabel(subtitle, self)
        self.subtitleLabel.setWordWrap(True)
        self.subtitleLabel.setTextColor(QColor("#e2dce2"), QColor("#e2dce2"))
        layout.addWidget(eyebrow)
        layout.addWidget(self.titleLabel)
        layout.addWidget(self.subtitleLabel)
        self.actionLayout = QHBoxLayout()
        self.actionLayout.setSpacing(8)
        self.actionLayout.addStretch()
        layout.addLayout(self.actionLayout)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), 18, 18)
        painter.setClipPath(clip)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor("#252b3c"))
        gradient.setColorAt(0.62, QColor("#453040"))
        gradient.setColorAt(1, QColor("#923e38"))
        painter.fillRect(self.rect(), gradient)
        # A circuit drawing stays in the right-hand artwork area on small windows.
        painter.setClipRect(self.width() - 250, 0, 250, self.height())
        painter.translate(self.width() - 115, self.height() / 2)
        painter.rotate(-16)
        painter.setPen(QPen(QColor(255, 195, 173, 42), 1.2))
        painter.setBrush(QColor(255, 176, 145, 14))
        painter.drawRoundedRect(QRectF(-48, -48, 96, 96), 14, 14)
        painter.drawRoundedRect(QRectF(-32, -32, 64, 64), 8, 8)
        for index in range(-2, 3):
            offset = index * 15
            for side in (-1, 1):
                path = QPainterPath(QPointF(side * 48, offset))
                path.lineTo(side * (76 + abs(index) * 8), offset)
                path.lineTo(side * (98 + abs(index) * 8), offset + 22)
                path.lineTo(side * 150, offset + 22)
                painter.drawPath(path)
                painter.drawEllipse(QPointF(side * 150, offset + 22), 3, 3)


class ShortcutCard(SimpleCardWidget):
    def __init__(self, icon, title, subtitle, parent=None):
        super().__init__(parent)
        self.setBorderRadius(14)
        self.setClickEnabled(True)
        self.setCursor(Qt.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        layout.addWidget(IconTile(icon, self, 44))
        text = QVBoxLayout()
        text.setSpacing(4)
        text.addWidget(StrongBodyLabel(title, self))
        subtitleLabel = CaptionLabel(subtitle, self)
        subtitleLabel.setWordWrap(True)
        text.addWidget(subtitleLabel)
        layout.addLayout(text, 1)
        arrow = IconWidget(FIF.CHEVRON_RIGHT, self)
        arrow.setFixedSize(12, 12)
        layout.addWidget(arrow)


class ResponsiveColumns(QWidget):
    """Two columns on wide windows; preserve readable controls when stacked."""
    def __init__(self, left, right, parent=None, breakpoint=1020):
        super().__init__(parent)
        self.breakpoint = breakpoint
        self.columns = QBoxLayout(QBoxLayout.LeftToRight, self)
        self.columns.setContentsMargins(0, 0, 0, 0)
        self.columns.setSpacing(16)
        self.columns.addWidget(left, 1, Qt.AlignTop)
        self.columns.addWidget(right, 1, Qt.AlignTop)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

    def resizeEvent(self, event):
        direction = QBoxLayout.LeftToRight if self.width() >= self.breakpoint else QBoxLayout.TopToBottom
        self.columns.setDirection(direction)
        super().resizeEvent(event)


class FirmwareDropZone(QWidget):
    fileDropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._dragging = False
        self._name = ""
        self.setMinimumHeight(112)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.addWidget(IconTile(FIF.DOCUMENT, self, 48))
        text = QVBoxLayout()
        text.setSpacing(5)
        self.titleLabel = StrongBodyLabel("将固件文件拖到这里", self)
        self.titleLabel.setWordWrap(True)
        self.subtitleLabel = CaptionLabel("或点击下方“浏览”选择文件", self)
        self.subtitleLabel.setWordWrap(True)
        text.addWidget(self.titleLabel)
        text.addWidget(self.subtitleLabel)
        layout.addLayout(text, 1)

    def setFile(self, path=""):
        self._name = Path(path).name if path else ""
        self.titleLabel.setText(self._name or "将固件文件拖到这里")
        self.subtitleLabel.setText("已载入固件 · 开始前将再次核对文件" if path else "或点击下方“浏览”选择文件")
        self.update()

    def _file(self, mime):
        urls = mime.urls() if mime.hasUrls() else []
        if len(urls) == 1 and urls[0].isLocalFile():
            path = Path(urls[0].toLocalFile())
            if path.is_file() and path.suffix.lower() in (".ota", ".bin", ".hex"):
                return str(path)
        return ""

    def dragEnterEvent(self, event):
        if self.isEnabled() and self._file(event.mimeData()):
            self._dragging = True
            event.acceptProposedAction()
            self.update()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._dragging = False
        self.update()
        event.accept()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        self._dragging = False
        self.update()
        path = self._file(event.mimeData()) if self.isEnabled() else ""
        if path:
            event.acceptProposedAction()
            self.fileDropped.emit(path)
        else:
            event.ignore()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(245, 109, 91, 18 if self._dragging else 8))
        color = QColor("#ef947b") if self._dragging else QColor(150, 150, 150, 90)
        painter.setPen(QPen(color, 1, Qt.SolidLine if self._name else Qt.DashLine))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 13, 13)


class TaskSteps(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.titles = ("准备", "上传", "烧录 / 安装", "完成确认")
        self.stage = -1
        self.outcome = None
        self.setFixedHeight(76)
        self.setMinimumWidth(300)
        setFont(self, 12)

    def setState(self, stage=-1, outcome=None):
        self.stage, self.outcome = stage, outcome
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setFont(self.font())
        muted = QColor("#959da9" if isDarkTheme() else "#738096")
        accent = QColor("#f49c87" if isDarkTheme() else "#b44933")
        green = QColor("#6ed6ab" if isDarkTheme() else "#147d56")
        line = QColor("#4b4f58" if isDarkTheme() else "#dce1e8")
        step = self.width() / 4
        for index, title in enumerate(self.titles):
            x = (index + 0.5) * step
            complete = self.outcome is True or index < self.stage
            active = index == self.stage
            color = green if complete else accent if active else muted
            if self.outcome is False and active:
                color = QColor("#ed7373" if isDarkTheme() else "#be3636")
            if index < 3:
                painter.setPen(QPen(green if complete else line, 2))
                painter.drawLine(QPointF(x + 18, 22), QPointF(x + step - 18, 22))
            painter.setPen(QPen(color if active or complete else line, 1.5))
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 24))
            painter.drawEllipse(QPointF(x, 22), 12, 12)
            painter.setPen(color)
            painter.drawText(QRectF(x - 12, 9, 24, 26), Qt.AlignCenter,
                             "✓" if complete else "!" if active and self.outcome is False else str(index + 1))
            painter.drawText(QRectF(index * step, 44, step, 24), Qt.AlignCenter, title)


def metric_box(title, label, parent):
    box = SimpleCardWidget(parent)
    box.setBorderRadius(10)
    layout = QVBoxLayout(box)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(6)
    layout.addWidget(CaptionLabel(title, box))
    setFont(label, 13, QFont.DemiBold)
    label.setWordWrap(True)
    layout.addWidget(label)
    return box
