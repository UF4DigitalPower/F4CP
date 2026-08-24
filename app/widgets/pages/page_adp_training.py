# -*- coding: utf-8 -*-
"""ADP training page.

The page is intentionally UI-only. Capture, serial I/O, CSV persistence and
offline training are owned by ``AdpTrainingSession`` and communicated through
Qt events.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QCoreApplication, QEvent
from PyQt5.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    ComboBox,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    ScrollArea,
    StrongBodyLabel,
    TextEdit,
)

from app.manager import StyleSheet
from app.session.page_adp_training import (
    AdpCaptureConfig,
    AdpCaptureSavedEvent,
    AdpErrorEvent,
    AdpLogEvent,
    AdpPortsEvent,
    AdpRequestAction,
    AdpRequestEvent,
    AdpStateEvent,
    AdpTrainingConfig,
    AdpTrainingFinishedEvent,
    AdpTrainingSession,
)
from app.widgets.components import ChipTone, PageHeader, StatusChip
from config import CTX


class AdpTrainingPage(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AdpTrainingPage")
        root = self.scrollWidget = QWidget(self)
        root.setObjectName("adpTrainingScrollWidget")
        self.layout = QVBoxLayout(root)
        self.layout.setContentsMargins(24, 24, 24, 24)
        self.layout.setSpacing(14)

        header = PageHeader(
            "ADP 训练数据",
            "Forward 拓扑数据采集、CSV 数据集管理与离线 Actor-Critic 训练。",
            root,
        )
        self.connectionPill = StatusChip("未连接", ChipTone.DANGER, header)
        header.addAction(self.connectionPill)
        self.layout.addWidget(header)

        self._build_capture_card(root)
        self._build_action_card(root)
        self._build_monitor_card(root)

        self.setWidget(root)
        self.setWidgetResizable(True)
        StyleSheet.ADP_TRAINING_PAGE.apply(self)
        CTX.cfg.themeChanged.connect(self._onThemeChanged)

        self._session = AdpTrainingSession(self, self)
        self._post_request(AdpRequestAction.REFRESH_PORTS)

    def _build_capture_card(self, root: QWidget) -> None:
        card = CardWidget(root)
        card.setObjectName("AdpCaptureCard")
        grid = QGridLayout(card)
        grid.setContentsMargins(20, 18, 20, 20)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)

        self.port = ComboBox(card)
        self.port.setMinimumWidth(150)
        self.baud = ComboBox(card)
        self.baud.addItems(["921600", "460800", "230400", "115200"])
        self.refresh = PushButton("刷新串口", card)
        self.refresh.clicked.connect(
            lambda: self._post_request(AdpRequestAction.REFRESH_PORTS)
        )
        self.ilimit = LineEdit(card)
        self.ilimit.setText("20")
        self.epochs = LineEdit(card)
        self.epochs.setText("100")
        self.validation = LineEdit(card)
        self.validation.setText("0.20")
        self.seed = LineEdit(card)
        self.seed.setText("7")
        self.file = LineEdit(card)
        self.file.setText(str(self._default_dataset_path()))
        self.browse = PushButton("选择 CSV", card)
        self.browse.clicked.connect(self.choose_file)
        self.output = LineEdit(card)
        self.output.setText(str(self._default_output_path()))
        self.browse_output = PushButton("选择头文件", card)
        self.browse_output.clicked.connect(self.choose_output)

        grid.addWidget(StrongBodyLabel("采集配置", card), 0, 0, 1, 3)
        controls = [
            ("串口", self.port),
            ("波特率", self.baud),
            ("Ilimit (A)", self.ilimit),
            ("Epoch", self.epochs),
            ("验证比例", self.validation),
            ("Seed", self.seed),
            ("数据集", self.file),
            ("权重头文件", self.output),
        ]
        for row, (label, widget) in enumerate(controls, start=1):
            grid.addWidget(BodyLabel(label, card), row, 0)
            grid.addWidget(widget, row, 1)
        grid.addWidget(self.refresh, 1, 2)
        grid.addWidget(self.browse, 7, 2)
        grid.addWidget(self.browse_output, 8, 2)
        self.layout.addWidget(card)

    def _build_action_card(self, root: QWidget) -> None:
        card = CardWidget(root)
        card.setObjectName("AdpActionCard")
        actions = QHBoxLayout(card)
        actions.setContentsMargins(20, 16, 20, 16)
        actions.setSpacing(10)
        actions.addWidget(StrongBodyLabel("工作流", card))
        self.start = PrimaryPushButton("开始采集", card)
        self.start.clicked.connect(self.start_capture)
        self.stop = PushButton("停止并保存", card)
        self.stop.clicked.connect(
            lambda: self._post_request(AdpRequestAction.STOP_CAPTURE)
        )
        self.stop.setEnabled(False)
        self.train = PushButton("训练模型", card)
        self.train.clicked.connect(self.run_training)
        actions.addWidget(self.start)
        actions.addWidget(self.stop)
        actions.addWidget(self.train)
        actions.addStretch()
        self.layout.addWidget(card)

    def _build_monitor_card(self, root: QWidget) -> None:
        card = CardWidget(root)
        card.setObjectName("AdpMonitorCard")
        monitor_layout = QVBoxLayout(card)
        monitor_layout.setContentsMargins(20, 18, 20, 20)
        monitor_layout.addWidget(StrongBodyLabel("运行状态", card))
        self.status = BodyLabel("未采集", card)
        monitor_layout.addWidget(self.status)
        self.log = TextEdit(card)
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("训练进程输出与串口状态…")
        monitor_layout.addWidget(self.log, 1)
        self.layout.addWidget(card, 1)

    def _default_dataset_path(self) -> Path:
        path = CTX.dirs.base_dir / "data" / "adp" / "adp_forward_capture.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _default_output_path(self) -> Path:
        firmware = (
            CTX.dirs.base_dir.parent
            / "STM32G474RBT6"
            / "USER"
            / "ADP_Scheduler"
            / "adp_outer_weights.h"
        )
        if firmware.parent.exists():
            return firmware
        return CTX.dirs.base_dir / "data" / "adp" / "adp_outer_weights.h"

    def _post_request(self, action: AdpRequestAction, payload=None) -> None:
        QCoreApplication.postEvent(self._session, AdpRequestEvent(action, payload))

    def _onThemeChanged(self, *_):
        StyleSheet.ADP_TRAINING_PAGE.apply(self)

    def choose_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存训练数据",
            self.file.text(),
            "CSV (*.csv)",
        )
        if path:
            self.file.setText(path)

    def choose_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出 ADP 权重头文件",
            self.output.text(),
            "C Header (*.h)",
        )
        if path:
            self.output.setText(path)

    def start_capture(self):
        try:
            config = AdpCaptureConfig(
                port=self.port.currentText().strip(),
                baudrate=int(self.baud.currentText()),
                dataset=Path(self.file.text().strip()),
            )
        except (TypeError, ValueError):
            self.status.setText("采集参数无效")
            return
        self._post_request(AdpRequestAction.START_CAPTURE, config)

    def run_training(self):
        try:
            ilimit = float(self.ilimit.text())
            epochs = int(self.epochs.text())
            validation_ratio = float(self.validation.text())
            seed = int(self.seed.text())
            if ilimit <= 0 or epochs < 1 or not 0 < validation_ratio < 0.5:
                raise ValueError
            output = Path(self.output.text().strip())
            config = AdpTrainingConfig(
                dataset=Path(self.file.text().strip()),
                ilimit=ilimit,
                epochs=epochs,
                validation_ratio=validation_ratio,
                seed=seed,
                output=output,
                report=output.with_suffix(".json"),
            )
        except (TypeError, ValueError):
            self.status.setText("训练参数无效，请检查 Ilimit、Epoch、验证比例和 Seed")
            return
        self._post_request(AdpRequestAction.START_TRAINING, config)

    def event(self, event: QEvent) -> bool:
        event_type = event.type()
        if event_type == AdpPortsEvent.EVENT_TYPE:
            ports = list(event.payload.ports)
            current = self.port.currentText()
            self.port.clear()
            self.port.addItems(ports or ["未发现串口"])
            if current in ports:
                self.port.setCurrentText(current)
            return True
        if event_type == AdpLogEvent.EVENT_TYPE:
            self.log.append(event.payload.text)
            return True
        if event_type == AdpErrorEvent.EVENT_TYPE:
            self.log.append(f"错误: {event.payload.text}")
            self.status.setText(event.payload.text)
            self._set_capture_buttons(False)
            return True
        if event_type == AdpStateEvent.EVENT_TYPE:
            self._handle_state(event.payload)
            return True
        if event_type == AdpCaptureSavedEvent.EVENT_TYPE:
            self.status.setText(
                f"已保存 {event.payload.rows} samples: {event.payload.path}"
            )
            self.log.append(f"训练数据已保存: {event.payload.path}")
            return True
        if event_type == AdpTrainingFinishedEvent.EVENT_TYPE:
            payload = event.payload
            self.train.setEnabled(True)
            self.status.setText(payload.message)
            if payload.success:
                self.log.append(f"权重已生成: {payload.output}")
                self.log.append(f"评估报告: {payload.report}")
            else:
                self.log.append(payload.message)
            return True
        return super().event(event)

    def _handle_state(self, payload) -> None:
        if payload.state == "capturing":
            self._set_capture_buttons(True)
            suffix = (
                f", 丢弃 {payload.dropped_frames} 帧"
                if payload.dropped_frames
                else ""
            )
            self.status.setText(f"采集中: {payload.rows} samples{suffix}")
            self.connectionPill.setText("已连接")
            self.connectionPill.setTone(ChipTone.SUCCESS)
        elif payload.state == "training":
            self.train.setEnabled(False)
            self._set_capture_buttons(False)
            self.status.setText("训练中...")
        else:
            self._set_capture_buttons(False)
            self.connectionPill.setText("未连接")
            self.connectionPill.setTone(ChipTone.DANGER)

    def _set_capture_buttons(self, capturing: bool) -> None:
        self.start.setEnabled(not capturing)
        self.stop.setEnabled(capturing)

    def closeEvent(self, event):
        self._session.shutdown()
        super().closeEvent(event)
