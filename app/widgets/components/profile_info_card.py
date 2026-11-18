"""Native QFluentWidgets expansion, with sizing for wrapping profile values."""
from PyQt5.QtCore import QAbstractAnimation, QEvent, QTimer, Qt
from PyQt5.QtWidgets import QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import SimpleExpandGroupSettingCard


class ProfileInfoCard(SimpleExpandGroupSettingCard):
    def __init__(self, icon, title, subtitle="", parent=None):
        super().__init__(icon, title, subtitle or None, parent)
        self.contentWidget = QWidget(self.view)
        self.bodyLayout = QVBoxLayout(self.contentWidget)
        self.bodyLayout.setContentsMargins(22, 18, 22, 22)
        self.bodyLayout.setSpacing(16)
        self.viewLayout.setAlignment(Qt.AlignTop)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.addGroupWidget(self.contentWidget)
        self.card.setCursor(Qt.PointingHandCursor)
        button = self.card.expandButton
        button.setFocusPolicy(Qt.StrongFocus)
        button.setAccessibleName(title)
        button.installEventFilter(self)
        self.expandAni.finished.connect(self._updateActionText)
        self._updateActionText()

    def _updateActionText(self):
        action = "收起" if self.isExpand else "展开"
        self.card.expandButton.setToolTip(action)
        self.card.expandButton.setAccessibleDescription(action + "此信息卡片")

    def refreshContent(self):
        width = max(1, self.viewport().width())
        layout = self.bodyLayout
        height = layout.totalHeightForWidth(width) if layout.hasHeightForWidth() else layout.sizeHint().height()
        self.contentWidget.setFixedHeight(max(0, height))
        self.view.setFixedHeight(max(0, height))
        self.viewLayout.activate()
        self._adjustViewSize()
        if self.expandAni.state() != QAbstractAnimation.Running and self.isExpand:
            self.verticalScrollBar().setValue(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width():
            QTimer.singleShot(0, self.refreshContent)

    def eventFilter(self, obj, event):
        if obj is self.card.expandButton and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                obj.click()
                return True
        return super().eventFilter(obj, event)
