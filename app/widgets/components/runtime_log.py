"""One modeless viewer for the application's existing shared log stream."""
import logging
from pathlib import Path
import weakref

from PyQt5.QtCore import QObject, Qt, pyqtSignal
from PyQt5.QtWidgets import QApplication, QDialog, QFileDialog, QHBoxLayout, QMessageBox, QVBoxLayout
from qfluentwidgets import CaptionLabel, PlainTextEdit, PushButton, SubtitleLabel, isDarkTheme


class _LogBridge(QObject):
    record = pyqtSignal(str)


class _LogHandler(logging.Handler):
    def __init__(self, bridge):
        super().__init__()
        self.bridge = weakref.ref(bridge)
        self.setFormatter(logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%H:%M:%S"))

    def emit(self, record):
        bridge = self.bridge()
        if bridge is not None:
            try:
                bridge.record.emit(self.format(record))
            except RuntimeError:
                pass  # The parent window may be closing on the UI thread.


class RuntimeLogDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("F4CP · 运行日志")
        self.setModal(False)
        self.resize(900, 560)
        self.setMinimumSize(640, 360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(SubtitleLabel("运行日志", self))
        layout.addWidget(CaptionLabel("连接、通信、下载与诊断集中记录于此。关闭窗口不影响任务，导出可保存完整记录。", self))
        self.logEdit = PlainTextEdit(self)
        self.logEdit.setReadOnly(True)
        self.logEdit.document().setMaximumBlockCount(1500)
        layout.addWidget(self.logEdit, 1)
        row = QHBoxLayout()
        self.fileLabel = CaptionLabel(self)
        self.fileLabel.setWordWrap(True)
        self.fileLabel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(self.fileLabel, 1)
        self.copyButton = PushButton("复制全部", self)
        self.saveButton = PushButton("导出日志", self)
        self.clearButton = PushButton("清空显示", self)
        for button in (self.copyButton, self.saveButton, self.clearButton):
            row.addWidget(button)
        layout.addLayout(row)
        self.copyButton.clicked.connect(lambda: QApplication.clipboard().setText(self.logEdit.toPlainText()))
        self.saveButton.clicked.connect(self._save)
        self.clearButton.clicked.connect(self.logEdit.clear)
        logger = logging.getLogger("F4CP")
        self.logFile = next((Path(h.baseFilename) for h in logger.handlers
                             if isinstance(h, logging.FileHandler)), None)
        self.fileLabel.setText("日志文件：" + str(self.logFile) if self.logFile else "显示本次运行记录")
        if self.logFile is not None and self.logFile.is_file():
            try:
                with self.logFile.open("rb") as stream:
                    stream.seek(max(0, self.logFile.stat().st_size - 256 * 1024))
                    self.logEdit.setPlainText(stream.read().decode("utf-8", errors="replace"))
            except OSError:
                pass
        self._bridge = _LogBridge(self)
        self._bridge.record.connect(self._append)
        self._handler = _LogHandler(self._bridge)
        logger.addHandler(self._handler)
        handler = self._handler
        self.destroyed.connect(lambda: (logger.removeHandler(handler), handler.close()))

    def _append(self, text):
        bar = self.logEdit.verticalScrollBar()
        following = bar.value() >= bar.maximum() - 4
        previous = bar.value()
        self.logEdit.appendPlainText(text)
        bar.setValue(bar.maximum() if following else previous)

    def open_log(self):
        self.setStyleSheet("QDialog { background: #202020; }" if isDarkTheme()
                           else "QDialog { background: #f8f8f8; }")
        self.show()
        self.raise_()
        self.activateWindow()

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出运行日志", "F4CP.log", "日志文件 (*.log)")
        if path:
            try:
                destination = Path(path)
                if self.logFile is not None and self.logFile.is_file():
                    if destination.resolve() == self.logFile.resolve():
                        QMessageBox.information(self, "日志已保存", "所选文件就是当前运行日志，无需覆盖。")
                        return
                    destination.write_bytes(self.logFile.read_bytes())
                else:
                    destination.write_text(self.logEdit.toPlainText(), encoding="utf-8")
            except OSError as exc:
                QMessageBox.warning(self, "日志导出失败", str(exc))
