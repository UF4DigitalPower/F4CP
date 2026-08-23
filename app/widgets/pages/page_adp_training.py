# -*- coding: utf-8 -*-
"""ADP training-data capture and offline training page."""
from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

from PyQt5.QtCore import QProcess, QTimer
from PyQt5.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (BodyLabel, CardWidget, CaptionLabel, ComboBox,
                             LineEdit, PrimaryPushButton, PushButton,
                             ScrollArea, StrongBodyLabel, TextEdit)

from app.protocol.uf4com import (Uf4Command, Uf4Flag, Uf4FrameParser,
                                 build_frame, encode_tv, iter_tv_items)
from app.session.page_device.other_device import listSerialPorts
from app.manager import StyleSheet
from app.widgets.components import PageHeader, StatusChip, ChipTone
from config import CTX

try:
    import serial
except Exception:  # pragma: no cover - optional until capture is used
    serial = None

STREAM_IDS = (0x11, 0x0A, 0x0C, 0x0B, 0x0D, 0x2A, 0x2D)
CSV_FIELDS = (
    "episode",
    "step",
    "vref_v",
    "vin_v",
    "vout_v",
    "iin_a",
    "iout_a",
    "iref_applied_a",
)


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

        card = CardWidget(root)
        card.setObjectName("AdpCaptureCard")
        grid = QGridLayout(card)
        grid.setContentsMargins(20, 18, 20, 20)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        self.port = ComboBox(card); self.port.setMinimumWidth(150)
        self.baud = ComboBox(card); self.baud.addItems(["115200", "230400", "460800", "921600"])
        self.refresh = PushButton("刷新串口", card); self.refresh.clicked.connect(self.refresh_ports)
        self.ilimit = LineEdit(card); self.ilimit.setText("20")
        self.epochs = LineEdit(card); self.epochs.setText("100")
        self.validation = LineEdit(card); self.validation.setText("0.20")
        self.seed = LineEdit(card); self.seed.setText("7")
        self.file = LineEdit(card)
        self.file.setText(str(self._default_dataset_path()))
        self.browse = PushButton("选择 CSV", card); self.browse.clicked.connect(self.choose_file)
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
        for row, (label, widget) in enumerate(controls):
            row += 1
            grid.addWidget(BodyLabel(label, card), row, 0)
            grid.addWidget(widget, row, 1)
        grid.addWidget(self.refresh, 1, 2); grid.addWidget(self.browse, 4, 2)
        grid.addWidget(self.browse_output, 8, 2)
        self.layout.addWidget(card)

        actionCard = CardWidget(root)
        actionCard.setObjectName("AdpActionCard")
        actions = QHBoxLayout(actionCard)
        actions.setContentsMargins(20, 16, 20, 16)
        actions.setSpacing(10)
        actions.addWidget(StrongBodyLabel("工作流", actionCard))
        self.start = PrimaryPushButton("开始采集", root); self.start.clicked.connect(self.start_capture)
        self.stop = PushButton("停止并保存", root); self.stop.clicked.connect(self.stop_capture); self.stop.setEnabled(False)
        self.train = PushButton("训练模型", root); self.train.clicked.connect(self.run_training)
        actions.addWidget(self.start); actions.addWidget(self.stop); actions.addWidget(self.train); actions.addStretch()
        self.layout.addWidget(actionCard)
        monitorCard = CardWidget(root)
        monitorCard.setObjectName("AdpMonitorCard")
        monitorLayout = QVBoxLayout(monitorCard)
        monitorLayout.setContentsMargins(20, 18, 20, 20)
        monitorLayout.addWidget(StrongBodyLabel("运行状态", monitorCard))
        self.status = BodyLabel("未采集", monitorCard); monitorLayout.addWidget(self.status)
        self.log = TextEdit(monitorCard); self.log.setReadOnly(True); self.log.setPlaceholderText("训练进程输出与串口状态…")
        monitorLayout.addWidget(self.log, 1); self.layout.addWidget(monitorCard, 1)
        self.setWidget(root); self.setWidgetResizable(True)
        StyleSheet.ADP_TRAINING_PAGE.apply(self)
        CTX.cfg.themeChanged.connect(self._onThemeChanged)

        self._port = None
        self._parser = Uf4FrameParser()
        self._rows = []
        self._step = 0
        self._process = None
        self._timer = QTimer(self)
        self._timer.setInterval(5)
        self._timer.timeout.connect(self.poll)
        self.refresh_ports()

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

    def refresh_ports(self):
        current = self.port.currentText(); self.port.clear()
        ports = listSerialPorts() or []
        self.port.addItems(ports or ["未发现串口"])
        if current in ports: self.port.setCurrentText(current)

    def _onThemeChanged(self, *_):
        StyleSheet.ADP_TRAINING_PAGE.apply(self)

    def choose_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存训练数据", self.file.text(), "CSV (*.csv)")
        if path: self.file.setText(path)

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
        if serial is None:
            self.status.setText("缺少 pyserial，无法打开串口")
            return
        try:
            self._port = serial.Serial(self.port.currentText(), int(self.baud.currentText()), timeout=0)
            self._parser = Uf4FrameParser(); self._rows = []; self._step = 0
            payload = b"".join(encode_tv(i, 0) for i in STREAM_IDS)
            frame = build_frame(Uf4Command.STREAM_START_REQ, 1, payload, int(Uf4Flag.ACK_REQ))
            self._port.write(frame); self._timer.start()
            self.log.append(f"STREAM_START -> {self.port.currentText()} ({len(STREAM_IDS)} fields)")
            self.start.setEnabled(False); self.stop.setEnabled(True)
            self.connectionPill.setText("已连接"); self.connectionPill.setTone(ChipTone.SUCCESS)
            self.status.setText("采集中: 0 samples")
        except Exception as exc:
            self.status.setText(f"打开串口失败: {exc}"); self._close_port()

    def poll(self):
        if not self._port: return
        try:
            data = self._port.read(self._port.in_waiting or 1)
            for frame in self._parser.feed(data):
                if int(frame.cmd) == int(Uf4Command.STREAM_DATA): self.accept_frame(frame.data)
        except Exception as exc:
            self.status.setText(f"串口读取失败: {exc}"); self.stop_capture()

    def accept_frame(self, payload):
        values = {item.id: item.value for item in iter_tv_items(payload, strict=False) if item.value is not None}
        if not all(i in values for i in STREAM_IDS): return
        self._step += 1
        self._rows.append({"episode": 0, "step": self._step,
                           "vref_v": values[0x11] / 1000.0,
                           "vin_v": values[0x0A] / 1000.0,
                           "vout_v": values[0x0C] / 1000.0,
                           "iin_a": values[0x0B] / 1000.0,
                           "iout_a": values[0x0D] / 1000.0,
                           "iref_applied_a": values[0x2A] / 1000.0})
        self.status.setText(f"采集中: {len(self._rows)} samples")

    def stop_capture(self):
        if self._port:
            try:
                self._port.write(build_frame(Uf4Command.STREAM_STOP_REQ, 2, b"", int(Uf4Flag.ACK_REQ)))
                self.log.append("STREAM_STOP sent")
            except Exception: pass
        self._timer.stop(); self._close_port(); self.start.setEnabled(True); self.stop.setEnabled(False)
        self.connectionPill.setText("未连接"); self.connectionPill.setTone(ChipTone.DANGER)
        if self._rows:
            dataset = Path(self.file.text())
            dataset.parent.mkdir(parents=True, exist_ok=True)
            with dataset.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS); writer.writeheader(); writer.writerows(self._rows)
        self.status.setText(f"已保存 {len(self._rows)} samples: {self.file.text()}")

    def stop_capture_and_save(self): self.stop_capture()

    def _close_port(self):
        if self._port:
            try: self._port.close()
            except Exception: pass
        self._port = None

    def run_training(self):
        if self._port: self.stop_capture()
        dataset = Path(self.file.text())
        script = Path(__file__).parents[2] / "tools" / "adp_offline_train.py"
        output = Path(self.output.text())
        report = output.with_suffix(".json")
        if not dataset.exists():
            self.status.setText("请先采集或选择 CSV 数据集")
            return
        if not getattr(sys, "frozen", False) and not script.exists():
            self.status.setText(f"训练器不存在: {script}")
            return
        try:
            ilimit = float(self.ilimit.text())
            epochs = int(self.epochs.text())
            validation = float(self.validation.text())
            seed = int(self.seed.text())
            if ilimit <= 0 or epochs < 1 or not 0 < validation < 0.5:
                raise ValueError
        except ValueError:
            self.status.setText("训练参数无效，请检查 Ilimit、Epoch、验证比例和 Seed")
            return
        output.parent.mkdir(parents=True, exist_ok=True)
        args = [
            "--dataset", str(dataset),
            "--ilimit", str(ilimit),
            "--epochs", str(epochs),
            "--validation-ratio", str(validation),
            "--seed", str(seed),
            "--output", str(output),
            "--report", str(report),
        ]
        if getattr(sys, "frozen", False):
            program = sys.executable
            args.insert(0, "--adp-train")
            workdir = CTX.dirs.base_dir
        else:
            program = sys.executable
            args.insert(0, str(script))
            workdir = script.parent.parent
        self.log.append("启动训练: " + " ".join(args))
        self._process = QProcess(self)
        self._process.setWorkingDirectory(str(workdir))
        self._process.setProgram(program)
        self._process.setArguments(args)
        self._process.readyReadStandardOutput.connect(
            lambda: self.log.append(
                bytes(self._process.readAllStandardOutput()).decode(errors="replace").rstrip()
            )
        )
        self._process.readyReadStandardError.connect(
            lambda: self.log.append(
                bytes(self._process.readAllStandardError()).decode(errors="replace").rstrip()
            )
        )
        self._process.finished.connect(
            lambda code, status: self._training_finished(code, output)
        )
        self.train.setEnabled(False)
        self.status.setText("训练中...")
        self._process.start()

    def _training_finished(self, exit_code, output):
        self.train.setEnabled(True)
        if int(exit_code) == 0:
            self.status.setText(f"训练完成: {output}")
            self.log.append(f"训练成功，权重已生成: {output}")
            self.log.append(f"评估报告: {output.with_suffix('.json')}")
        else:
            self.status.setText(f"训练失败，退出码 {exit_code}")
            self.log.append(f"训练失败，退出码: {exit_code}")

    def closeEvent(self, event):
        self.stop_capture(); super().closeEvent(event)
