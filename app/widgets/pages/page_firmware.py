"""One firmware workspace for V208/G474, wired and authenticated wireless transfers."""
import logging
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, ComboBox, InfoBar, LineEdit,
    FluentIcon as FIF, PrimaryPushButton, ProgressBar, PushButton, ScrollArea)

from app.protocol.firmware_download import G474, V208, WIRED, WIRELESS, load_firmware
from .page_layout import page_content, section
from .device_connection_panel import DeviceConnectionPanel
from app.session.pyocd_programmer import PyOcdWorker
from config import CTX
from app.widgets.components.runtime_log import RuntimeLogDialog
from app.widgets.components.chip import ChipTone, StatusChip
from app.widgets.components.workspace_widgets import FirmwareDropZone, ResponsiveColumns, TaskSteps, metric_box

LOGGER = logging.getLogger("F4CP.Firmware")


class FirmwarePage(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logDialog = RuntimeLogDialog(self)
        self.blePanel = DeviceConnectionPanel(self)
        self.controller = self.blePanel.controller
        self._pyocd_worker = None
        self._pyocd_action = ""
        self._pyocd_outcome = None
        self._active = self._can_cancel = False
        self._path = ""
        self._firmware = None
        content, layout = page_content(self, "FirmwarePage", "固件下载", "连接设备，选择镜像，跟踪每一步写入与校验。")
        card, body = section(content, "01  连接与目标", "选择芯片与传输方式", icon=FIF.CONNECT)
        self.connectionCard = card
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        self.targetCombo = ComboBox(card)
        self.targetCombo.addItem("CH32V208RBT6", userData=V208)
        self.targetCombo.addItem("STM32G474RBT6", userData=G474)
        self.modeCombo = ComboBox(card)
        self.modeCombo.addItem("无线（BLE）", userData=WIRELESS)
        grid.addWidget(CaptionLabel("目标芯片", card), 0, 0)
        grid.addWidget(self.targetCombo, 1, 0)
        grid.addWidget(CaptionLabel("连接方式", card), 2, 0)
        grid.addWidget(self.modeCombo, 3, 0)
        body.addLayout(grid)
        self.hintLabel = CaptionLabel(card)
        self.hintLabel.setWordWrap(True)
        connection_body = body
        self.wirelessCard = self.blePanel
        self.connectionLabel = self.blePanel.connectionLabel
        connection_body.addWidget(self.wirelessCard)

        self.pyocdCard = QWidget(card)
        probe_layout = QVBoxLayout(self.pyocdCard)
        probe_layout.setContentsMargins(0, 0, 0, 0)
        probe_layout.setSpacing(10)
        row = QHBoxLayout()
        self.probeCombo = ComboBox(self.pyocdCard)
        self.probeCombo.setPlaceholderText("请扫描 DAPLink 探针")
        self.scanProbeButton = PushButton(FIF.SYNC, "扫描探针", self.pyocdCard)
        self.connectProbeButton = PushButton(FIF.LINK, "连接 / 识别", self.pyocdCard)
        probe_layout.addWidget(self.probeCombo)
        row.addWidget(self.scanProbeButton)
        row.addWidget(self.connectProbeButton)
        row.addStretch()
        probe_layout.addLayout(row)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        self.frequencyCombo = ComboBox(self.pyocdCard)
        for text, value in (("100 kHz", 100000), ("500 kHz", 500000), ("1 MHz", 1000000), ("4 MHz", 4000000)):
            self.frequencyCombo.addItem(text, userData=value)
        self.connectModeCombo = ComboBox(self.pyocdCard)
        self.connectModeCombo.addItems(["under-reset", "halt", "pre-reset", "attach"])
        grid.addWidget(CaptionLabel("SWD 频率", self.pyocdCard), 0, 0)
        grid.addWidget(self.frequencyCombo, 0, 1)
        grid.addWidget(CaptionLabel("连接模式", self.pyocdCard), 1, 0)
        grid.addWidget(self.connectModeCombo, 1, 1)
        grid.setColumnStretch(1, 1)
        probe_layout.addLayout(grid)
        self.probeInfoLabel = CaptionLabel("pyOCD · STM32G474RBTx · 本地 STM32G4 Pack", self.pyocdCard)
        self.probeInfoLabel.setWordWrap(True)
        probe_layout.addWidget(self.probeInfoLabel)
        self.scanProbeButton.clicked.connect(lambda: self._start_pyocd("scan"))
        self.connectProbeButton.clicked.connect(lambda: self._start_pyocd("connect"))
        connection_body.addWidget(self.pyocdCard)
        connection_body.addWidget(self.hintLabel)
        card, body = section(content, "02  固件与任务", "拖放或浏览选择所需固件", icon=FIF.DOWNLOAD)
        self.downloadCard = card
        self.dropZone = FirmwareDropZone(card)
        self.dropZone.fileDropped.connect(self._select_file)
        body.addWidget(self.dropZone)
        row = QHBoxLayout()
        self.pathEdit = LineEdit(card)
        self.pathEdit.setReadOnly(True)
        self.pathEdit.setPlaceholderText("请选择固件文件")
        self.fileButton = PushButton(FIF.FOLDER, "浏览", card)
        self.startButton = PrimaryPushButton(FIF.DOWNLOAD, "开始下载", card)
        self.cancelButton = PushButton(FIF.CANCEL, "取消上传", card)
        row.addWidget(self.pathEdit, 1)
        row.addWidget(self.fileButton)
        body.addLayout(row)
        self.packageLabel = CaptionLabel("尚未选择固件", card)
        self.packageLabel.setWordWrap(True)
        self.progressBar = ProgressBar(card)
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)
        self.progressLabel = CaptionLabel("等待下载", card)
        self.progressLabel.setWordWrap(True)
        self.phaseLabel = BodyLabel("就绪", card)
        self.phaseLabel.setWordWrap(True)
        body.addWidget(self.packageLabel)
        self.taskSteps = TaskSteps(card)
        body.addWidget(self.taskSteps)
        phase_row = QHBoxLayout()
        phase_row.addWidget(self.phaseLabel, 1)
        self.taskChip = StatusChip("等待开始", parent=card)
        phase_row.addWidget(self.taskChip, 0, Qt.AlignRight)
        body.addLayout(phase_row)
        self.resultLabel = BodyLabel(card)
        self.resultLabel.setWordWrap(True)
        self.resultLabel.hide()
        body.addWidget(self.resultLabel)
        body.addWidget(self.progressBar)
        metrics = QHBoxLayout()
        self.speedLabel = CaptionLabel("速度 —", card)
        self.remainingLabel = CaptionLabel("剩余时间 —", card)
        metrics.setSpacing(8)
        metrics.addWidget(metric_box("传输数据", self.progressLabel, card), 1)
        metrics.addWidget(metric_box("上传速度", self.speedLabel, card), 1)
        metrics.addWidget(metric_box("预计剩余", self.remainingLabel, card), 1)
        body.addLayout(metrics)
        actions = QHBoxLayout()
        self.validationLabel = CaptionLabel("写入校验 · 完成后复位运行", card)
        body.addWidget(self.validationLabel)
        actions.addStretch()
        actions.addWidget(self.cancelButton)
        actions.addWidget(self.startButton)
        body.addLayout(actions)
        self.workspace = ResponsiveColumns(self.connectionCard, self.downloadCard, content)
        layout.addWidget(self.workspace)
        layout.addStretch()

        self.fileButton.clicked.connect(self._file)
        self.startButton.clicked.connect(self._start)
        self.cancelButton.clicked.connect(self._cancel)
        self.targetCombo.currentIndexChanged.connect(self._selection)
        self.modeCombo.currentIndexChanged.connect(self._selection)
        self.probeCombo.currentIndexChanged.connect(self._sync)
        self.blePanel.stateChanged.connect(self._sync)
        self.controller.phase.connect(self._phase)
        self.controller.progress.connect(self._progress)
        self.controller.result.connect(self._result)
        self.controller.busy.connect(self._busy_changed)
        self.controller.version.connect(lambda text: self._sync())
        self._selection()

    @property
    def target(self):
        return self.targetCombo.currentData()

    @property
    def wireless(self):
        return self.modeCombo.currentData() == WIRELESS

    def _selection(self, *_):
        v208 = self.target == V208
        modes = [WIRELESS] if v208 else [WIRELESS, WIRED]
        if [self.modeCombo.itemData(i) for i in range(self.modeCombo.count())] != modes:
            previous = self.modeCombo.currentData()
            self.modeCombo.blockSignals(True)
            self.modeCombo.clear()
            self.modeCombo.addItem("无线（BLE）", userData=WIRELESS)
            if not v208:
                self.modeCombo.addItem("有线（DAPLink / pyOCD）", userData=WIRED)
            self.modeCombo.setCurrentIndex(modes.index(previous) if previous in modes else 0)
            self.modeCombo.blockSignals(False)
        self.pyocdCard.setVisible(not self.wireless and not v208)
        self.wirelessCard.setVisible(self.wireless)
        if self.wireless:
            hint = ("V208：选择 .ota 包；安装后自动重连，核对运行版本、长度和 CRC32。" if v208 else
                    "G474：选择从 0x08000000 链接的 BIN，最大 128 KiB；需要支持 G474 下载的 Link V3 固件。目标擦写后读回校验。")
        else:
            hint = "G474：使用 pyOCD 连接 DAPLink，支持 HEX / BIN，最大 128 KiB；下载后完整读回校验。"
        self.hintLabel.setText(hint)
        self._clear_file()

    def _clear_file(self, *_):
        self._path = ""
        self._firmware = None
        self.pathEdit.clear()
        self.packageLabel.setText("尚未选择固件")
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)
        self.progressLabel.setText("等待下载")
        self.phaseLabel.setText("就绪")
        self.speedLabel.setText("速度 —")
        self.remainingLabel.setText("剩余时间 —")
        self.dropZone.setFile()
        formats = ".ota 升级包" if self.target == V208 else ".bin 固件" if self.wireless else ".hex / .bin 固件"
        self.dropZone.subtitleLabel.setText("支持 " + formats + " · 也可点击下方“浏览”")
        self.taskSteps.titles = (("准备", "上传", "烧录 / 安装", "完成确认") if self.wireless else
                                 ("准备", "写入", "读回校验", "完成确认"))
        self.taskSteps.setState()
        self.taskChip.setText("等待开始")
        self.taskChip.setTone(ChipTone.NEUTRAL)
        self.resultLabel.clear()
        self.resultLabel.hide()
        self.validationLabel.setText("安装后自动重连 · 核对运行版本和 CRC32" if self.target == V208 else
                                     "完整读回校验 · 完成后复位运行")
        self._sync()

    def _sync(self, *_):
        idle = not self._active and not self.blePanel._busy and not self.blePanel._closing
        for widget in (self.targetCombo, self.fileButton,
                       self.probeCombo, self.scanProbeButton, self.frequencyCombo, self.connectModeCombo):
            widget.setEnabled(idle)
        self.dropZone.setEnabled(idle)
        self.modeCombo.setEnabled(idle and self.target == G474)
        ready = bool(self._firmware)
        if self.wireless:
            ready = ready and self.blePanel._connected and self.blePanel._flash_ready and self.controller.loop is not None
        else:
            ready = ready and self.target == G474 and bool(self.probeCombo.currentData())
        self.connectProbeButton.setEnabled(idle and bool(self.probeCombo.currentData()))
        self.startButton.setEnabled(idle and ready)
        self.cancelButton.setEnabled(self._active and self.wireless and self._can_cancel)

    def _start_pyocd(self, action, firmware=None):
        if self.target != G474 or self.wireless:
            return
        if self._pyocd_worker is not None or self.blePanel._busy:
            if action == "program":
                raise RuntimeError("连接任务尚未结束，请稍后下载")
            return
        if action != "program" and self._active:
            return
        if action != "scan" and not self.probeCombo.currentData():
            if action == "program":
                raise ValueError("请先扫描并选择 DAPLink 探针")
            self._notify(False, "请先扫描并选择 DAPLink 探针")
            return
        self._active = True
        self._can_cancel = False
        self._pyocd_action = action
        self._pyocd_outcome = None
        self.resultLabel.hide()
        self.blePanel._external_busy = True
        self.blePanel._sync()
        pack = CTX.dirs.McuPackDir / "UF4.STM32G4xx_DFP.2.2.0.pack"
        worker = PyOcdWorker(action, uid=self.probeCombo.currentData() or "", pack=str(pack),
                             frequency=self.frequencyCombo.currentData(),
                             connect_mode=self.connectModeCombo.currentText(), firmware=firmware, parent=self)
        self._pyocd_worker = worker
        worker.probes.connect(self._probes)
        worker.message.connect(self._pyocd_message)
        worker.progress.connect(self._wired_progress)
        worker.result.connect(self._pyocd_result)
        worker.finished.connect(self._pyocd_finished)
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)
        self.phaseLabel.setText({"scan": "正在扫描 DAPLink 探针…", "connect": "pyOCD 正在连接和识别 G474…",
                                    "program": "pyOCD 正在烧录 G474…"}[action])
        self.taskSteps.titles = ("准备", "写入", "读回校验", "完成确认")
        self._task_stage(1 if action == "program" else 0)
        worker.start()
        self._sync()

    def _pyocd_message(self, text):
        LOGGER.info(text)
        if "DEV_ID" in text:
            self.probeInfoLabel.setText(text)
        if text.startswith(("pyOCD 正在", "正在读回", "pyOCD 写入")):
            self.phaseLabel.setText(text)
            if self._pyocd_action == "program":
                self._task_stage(2 if "校验" in text or "读回" in text else 1)

    def _wired_progress(self, value):
        self.progressBar.setValue(value)
        self.progressLabel.setText(f"进度 {value}% · 等待完整校验" if value >= 85 else f"进度 {value}%")

    def _probes(self, probes):
        uid = self.probeCombo.currentData()
        self.probeCombo.clear()
        for probe in probes:
            self.probeCombo.addItem(f"{probe.description} · {probe.uid}", userData=probe.uid)
        for i in range(self.probeCombo.count()):
            if self.probeCombo.itemData(i) == uid:
                self.probeCombo.setCurrentIndex(i)
                break
        self.probeInfoLabel.setText(f"发现 {len(probes)} 个探针 · pyOCD · STM32G474RBTx · 本地 STM32G4 Pack")

    def _pyocd_result(self, success, text):
        self._pyocd_outcome = success, text

    def _pyocd_finished(self):
        worker, self._pyocd_worker = self._pyocd_worker, None
        outcome = self._pyocd_outcome or (False, "pyOCD 工作线程已结束，未确认操作成功")
        self._finish(*outcome)
        if self._pyocd_action != "program":
            self.progressBar.setValue(0)
            self.taskSteps.setState()
        worker.deleteLater()

    def shutdown(self):
        if self._pyocd_worker is not None and self._pyocd_worker.isRunning():
            return False
        return self.blePanel.shutdown()

    def _load(self, path):
        return load_firmware(path, self.target, WIRELESS if self.wireless else WIRED)

    def _file(self):
        filters = "OTA 固件 (*.ota)" if self.wireless and self.target == V208 else ("BIN 固件 (*.bin)" if self.wireless else "固件 (*.hex *.bin)")
        path, _ = QFileDialog.getOpenFileName(self, "选择固件", self._path, filters)
        if not path:
            return
        self._select_file(path)

    def _select_file(self, path):
        if self._active or self.blePanel._busy or self.blePanel._closing:
            return
        self._clear_file()
        try:
            self._firmware = self._load(path)
            self._path = path
            self.pathEdit.setText(path)
            self.dropZone.setFile(path)
            self.packageLabel.setText(self._firmware.summary)
            self.progressLabel.setText("文件检查通过")
            LOGGER.info("已选择固件：%s · %s · %s", self.targetCombo.currentText(), self.modeCombo.currentText(), self._firmware.summary)
        except Exception as exc:
            self._notify(False, str(exc))
        self._sync()

    def _start(self):
        if not self.startButton.isEnabled():
            return
        try:
            firmware = self._load(self._path)
            if firmware != self._firmware:
                self._clear_file()
                raise ValueError("固件文件已变化，请重新选择并核对")
            warning = ("开始上传并安装？" if self.target == V208 and self.wireless else
                       "将擦写所选芯片的固件区域。擦写期间请保持供电和连接，完成前不能退出。是否开始？")
            if QMessageBox.question(self, "确认固件下载", self.targetCombo.currentText() + "\n" + self.modeCombo.currentText() + "\n" + firmware.summary + "\n\n" + warning) != QMessageBox.Yes:
                return
            self._active = True
            self._can_cancel = self.wireless
            self.resultLabel.hide()
            self.progressBar.setRange(0, 100)
            self.progressBar.setValue(0)
            self.phaseLabel.setText("正在准备下载…")
            self.taskSteps.titles = ("准备", "上传", "烧录 / 安装", "完成确认")
            self._task_stage(0)
            self.progressLabel.setText("等待传输")
            self.speedLabel.setText("速度 —")
            self.remainingLabel.setText("剩余时间 —")
            LOGGER.info("开始下载：%s · %s · %s", self.targetCombo.currentText(), self.modeCombo.currentText(), firmware.summary)
            if self.wireless:
                if not self.controller.submit("upload" if self.target == V208 else "target_upload", firmware.data):
                    raise RuntimeError("设备正忙或连接线程未就绪")
            else:
                self._start_pyocd("program", firmware)
        except Exception as exc:
            self._finish(False, str(exc))
        self._sync()

    def _phase(self, text, can_cancel):
        if self._active and self.wireless:
            self._can_cancel = can_cancel
            self.phaseLabel.setText(text.split(" · ", 1)[0])
            if "完成" in text or "读回" in text:
                self._task_stage(3)
            elif "烧录" in text or "安装" in text or "SWD" in text or text.startswith(("擦除 G474", "写入 G474")):
                self._task_stage(2)
            elif "重连" in text:
                self._task_stage(3)
            elif "上传" in text or "CRC" in text:
                self._task_stage(1)
            LOGGER.info(text)
            if not can_cancel:
                self.remainingLabel.setText("等待校验与完成确认")
            self._sync()

    def _task_stage(self, stage):
        self.taskSteps.setState(stage)
        self.taskChip.setText("进行中")
        self.taskChip.setTone(ChipTone.NEUTRAL)

    def _progress(self, done, total, speed, remaining):
        if self._active and self.wireless:
            self.progressBar.setValue(done * 95 // max(1, total))
            self.progressLabel.setText(f"已上传 {done:,} / {total:,} B")
            self.speedLabel.setText(f"{speed / 1024:.1f} KiB/s")
            self.remainingLabel.setText(f"约 {remaining:.0f} 秒")

    def _result(self, success, text):
        if self._active and self.wireless:
            self._finish(success, text)

    def _busy_changed(self, busy):
        if not busy and self._active and self.wireless:
            self._finish(False, "下载已结束，未收到安装成功确认")
        self._sync()

    def _cancel(self):
        if self._active and self._can_cancel:
            self.controller.cancel()
            self._can_cancel = False
            self.phaseLabel.setText("正在取消上传…")
            self._sync()

    def _finish(self, success, text):
        self._active = self._can_cancel = False
        self.blePanel._external_busy = False
        self.blePanel._sync()
        self.progressBar.setRange(0, 100)
        if success:
            self.progressBar.setValue(100)
        completed = "下载完成" if self.wireless or self._pyocd_action == "program" else (
            "扫描完成" if self._pyocd_action == "scan" else "识别完成")
        self.phaseLabel.setText(completed if success else "操作未完成")
        self.resultLabel.setText(text)
        self.resultLabel.setTextColor("#147d56" if success else "#b91c1c", "#6ed6ab" if success else "#f49393")
        self.resultLabel.show()
        self.remainingLabel.setText("—")
        self.taskSteps.setState(max(0, self.taskSteps.stage), success)
        self.taskChip.setText("已完成" if success else "未完成")
        self.taskChip.setTone(ChipTone.SUCCESS if success else ChipTone.DANGER)
        (LOGGER.info if success else LOGGER.error)(text)
        self._notify(success, text)
        self._sync()

    def _notify(self, success, text):
        (InfoBar.success if success else InfoBar.error)("操作完成" if success else "操作未完成", text,
                                                      duration=6000 if success else -1, parent=self)
