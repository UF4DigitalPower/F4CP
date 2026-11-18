"""One firmware workspace for V208/G474, wired and authenticated wireless transfers."""
from PyQt5.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, ComboBox, InfoBar, LineEdit,
    FluentIcon as FIF, PrimaryPushButton, ProgressBar, PushButton, ScrollArea, TextEdit)

from app.protocol.firmware_download import G474, V208, WIRED, WIRELESS, load_firmware
from .page_layout import page_content, section
from .device_connection_panel import DeviceConnectionPanel
from app.session.pyocd_programmer import PyOcdWorker
from config import CTX


class FirmwarePage(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.blePanel = DeviceConnectionPanel(self)
        self.controller = self.blePanel.controller
        self._pyocd_worker = None
        self._pyocd_action = ""
        self._pyocd_outcome = None
        self._active = self._can_cancel = False
        self._path = ""
        self._firmware = None
        content, layout = page_content(self, "FirmwarePage", "固件下载", "V208 / G474 固件烧录与无线升级")

        card, body = section(content, "连接与目标", "")
        self.connectionCard = card
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        self.targetCombo = ComboBox(card)
        self.targetCombo.addItem("CH32V208RBT6", userData=V208)
        self.targetCombo.addItem("STM32G474RBT6", userData=G474)
        self.modeCombo = ComboBox(card)
        self.modeCombo.addItem("无线（BLE）", userData=WIRELESS)
        grid.addWidget(BodyLabel("目标芯片", card), 0, 0)
        grid.addWidget(self.targetCombo, 0, 1)
        grid.addWidget(BodyLabel("连接方式", card), 0, 2)
        grid.addWidget(self.modeCombo, 0, 3)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
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
        row.addWidget(self.probeCombo, 1)
        row.addWidget(self.scanProbeButton)
        row.addWidget(self.connectProbeButton)
        probe_layout.addLayout(row)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        self.frequencyCombo = ComboBox(self.pyocdCard)
        for text, value in (("100 kHz", 100000), ("500 kHz", 500000), ("1 MHz", 1000000), ("4 MHz", 4000000)):
            self.frequencyCombo.addItem(text, userData=value)
        self.connectModeCombo = ComboBox(self.pyocdCard)
        self.connectModeCombo.addItems(["under-reset", "halt", "pre-reset", "attach"])
        grid.addWidget(BodyLabel("SWD 频率", self.pyocdCard), 0, 0)
        grid.addWidget(self.frequencyCombo, 0, 1)
        grid.addWidget(BodyLabel("连接模式", self.pyocdCard), 0, 2)
        grid.addWidget(self.connectModeCombo, 0, 3)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        probe_layout.addLayout(grid)
        self.probeInfoLabel = CaptionLabel("pyOCD · STM32G474RBTx · 本地 STM32G4 Pack", self.pyocdCard)
        self.probeInfoLabel.setWordWrap(True)
        probe_layout.addWidget(self.probeInfoLabel)
        self.scanProbeButton.clicked.connect(lambda: self._start_pyocd("scan"))
        self.connectProbeButton.clicked.connect(lambda: self._start_pyocd("connect"))
        connection_body.addWidget(self.pyocdCard)
        connection_body.addWidget(self.hintLabel)
        layout.addWidget(card)

        card, body = section(content, "固件下载", "")
        self.downloadCard = card
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
        for widget in (self.packageLabel, self.progressBar, self.progressLabel):
            body.addWidget(widget)
        actions = QHBoxLayout()
        self.validationLabel = CaptionLabel("写入校验 · 完成后复位运行", card)
        actions.addWidget(self.validationLabel)
        actions.addStretch()
        actions.addWidget(self.cancelButton)
        actions.addWidget(self.startButton)
        body.addLayout(actions)
        layout.addWidget(card)
        card, body = section(content, "下载日志", "")
        self.log = TextEdit(card)
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(180)
        self.log.document().setMaximumBlockCount(600)
        body.addWidget(self.log)
        layout.addWidget(card)
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
        self.controller.message.connect(self._message)
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
        self._sync()

    def _sync(self, *_):
        idle = not self._active and not self.blePanel._busy and not self.blePanel._closing
        for widget in (self.targetCombo, self.fileButton,
                       self.probeCombo, self.scanProbeButton, self.frequencyCombo, self.connectModeCombo):
            widget.setEnabled(idle)
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
        self.blePanel._external_busy = True
        self.blePanel._sync()
        pack = CTX.dirs.McuPackDir / "UF4.STM32G4xx_DFP.2.2.0.pack"
        worker = PyOcdWorker(action, uid=self.probeCombo.currentData() or "", pack=str(pack),
                             frequency=self.frequencyCombo.currentData(),
                             connect_mode=self.connectModeCombo.currentText(), firmware=firmware, parent=self)
        self._pyocd_worker = worker
        worker.probes.connect(self._probes)
        worker.message.connect(self.log.append)
        worker.progress.connect(self.progressBar.setValue)
        worker.result.connect(self._pyocd_result)
        worker.finished.connect(self._pyocd_finished)
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)
        self.progressLabel.setText({"scan": "正在扫描 DAPLink 探针…", "connect": "pyOCD 正在连接和识别 G474…",
                                    "program": "pyOCD 正在烧录 G474…"}[action])
        worker.start()
        self._sync()

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
        self._clear_file()
        try:
            self._firmware = self._load(path)
            self._path = path
            self.pathEdit.setText(path)
            self.packageLabel.setText(self._firmware.summary)
            self.progressLabel.setText("文件检查通过")
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
            self.progressBar.setRange(0, 100)
            self.progressBar.setValue(0)
            self.progressLabel.setText("正在准备下载…")
            self.log.append(self.targetCombo.currentText() + " · " + self.modeCombo.currentText() + "\n" + firmware.summary)
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
            self.progressLabel.setText(text)
            self.log.append(text)
            self._sync()

    def _progress(self, done, total, speed, remaining):
        if self._active and self.wireless:
            self.progressBar.setValue(done * 95 // max(1, total))
            self.progressLabel.setText(f"正在上传 {done:,} / {total:,} B · {speed / 1024:.1f} KiB/s · 剩余约 {remaining:.0f} 秒")

    def _message(self, text):
        if self._active and self.wireless:
            self.log.append(text)

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
            self.progressLabel.setText("正在取消上传…")
            self._sync()

    def _finish(self, success, text):
        self._active = self._can_cancel = False
        self.blePanel._external_busy = False
        self.blePanel._sync()
        self.progressBar.setRange(0, 100)
        if success:
            self.progressBar.setValue(100)
        self.progressLabel.setText(text)
        self.log.append(text)
        self._notify(success, text)
        self._sync()

    def _notify(self, success, text):
        (InfoBar.success if success else InfoBar.error)("下载完成" if success else "操作未完成", text, duration=6000, parent=self)
