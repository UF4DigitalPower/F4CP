"""One firmware workspace for V208/G474, wired and authenticated wireless transfers."""
from pathlib import Path
import codecs
import shutil
import tempfile

from PyQt5.QtCore import QProcess, Qt
from PyQt5.QtWidgets import QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, ComboBox, InfoBar, LineEdit,
    FluentIcon as FIF, PrimaryPushButton, ProgressBar, PushButton, ScrollArea, TextEdit)

from app.protocol.firmware_download import G474, V208, WIRED, WIRELESS, load_firmware, openocd_command
from .page_home import page_content, section


class FirmwarePage(ScrollArea):
    def __init__(self, home, parent=None):
        super().__init__(parent)
        self.home = home
        self.controller = home.controller
        self._active = self._can_cancel = False
        self._path = ""
        self._firmware = self._temporary = None
        self._profiles = {V208: ["", "", ""], G474: [shutil.which("openocd") or "", "", ""]}
        self._previous_target = V208
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
        self.modeCombo.addItem("有线（USB 调试器）", userData=WIRED)
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
        self.wirelessCard = QWidget(card)
        body = QHBoxLayout(self.wirelessCard)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)
        self.connectionLabel = BodyLabel("未连接，请前往首页扫描并连接设备", self.wirelessCard)
        self.connectionLabel.setWordWrap(True)
        self.connectButton = PushButton(FIF.LINK, "连接设备", self.wirelessCard)
        self.connectButton.clicked.connect(lambda: self.window().switchTo(self.home))
        body.addWidget(BodyLabel("蓝牙状态", self.wirelessCard))
        body.addWidget(self.connectionLabel, 1)
        body.addWidget(self.connectButton)
        connection_body.addWidget(self.wirelessCard)

        self.wiredCard = QWidget(card)
        body = QVBoxLayout(self.wiredCard)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(8)
        form = QFormLayout()
        self.toolEdit = LineEdit(self.wiredCard)
        self.toolEdit.setPlaceholderText("选择 openocd.exe")
        self.toolButton = PushButton("浏览…", self.wiredCard)
        self.configEdit = LineEdit(self.wiredCard)
        self.configEdit.setPlaceholderText("WCH OpenOCD 同目录的 wch-riscv.cfg")
        self.configButton = PushButton("浏览…", self.wiredCard)
        self.serialEdit = LineEdit(self.wiredCard)
        self.serialEdit.setPlaceholderText("可选；多台调试器连接时填写指定序列号")
        self.baseCombo = ComboBox(self.wiredCard)
        self.baseCombo.addItem("0x00000000 · 完整镜像 / 独立固件", userData=0)
        self.baseCombo.addItem("0x00004000 · 仅应用，需已有兼容 Boot", userData=0x4000)
        for label, edit, button in (("OpenOCD", self.toolEdit, self.toolButton), ("WCH 配置", self.configEdit, self.configButton)):
            row = QHBoxLayout()
            row.addWidget(edit, 1)
            row.addWidget(button)
            form.addRow(BodyLabel(label, self.wiredCard), row)
        self.wiredForm = form
        form.addRow(BodyLabel("调试器序列号", self.wiredCard), self.serialEdit)
        form.addRow(BodyLabel("V208 BIN 地址", self.wiredCard), self.baseCombo)
        body.addLayout(form)
        self.toolButton.clicked.connect(self._tool)
        self.configButton.clicked.connect(self._config)
        connection_body.addWidget(self.wiredCard)
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

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._output)
        self.process.finished.connect(self._wired_finished)
        self.process.errorOccurred.connect(self._process_error)
        self.fileButton.clicked.connect(self._file)
        self.startButton.clicked.connect(self._start)
        self.cancelButton.clicked.connect(self._cancel)
        self.targetCombo.currentIndexChanged.connect(self._selection)
        self.modeCombo.currentIndexChanged.connect(self._selection)
        self.baseCombo.currentIndexChanged.connect(self._clear_file)
        self.toolEdit.textChanged.connect(self._sync)
        self.configEdit.textChanged.connect(self._sync)
        self.home.stateChanged.connect(self._sync)
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
        self._profiles[self._previous_target] = [self.toolEdit.text(), self.configEdit.text(), self.serialEdit.text()]
        self._previous_target = self.target
        tool, config, serial = self._profiles[self.target]
        self.toolEdit.setText(tool)
        self.configEdit.setText(config)
        self.serialEdit.setText(serial)
        v208 = self.target == V208
        for widget in (self.configEdit, self.configButton, self.baseCombo):
            widget.setVisible(v208)
        self.wiredForm.labelForField(self.baseCombo).setVisible(v208)
        # The config row is a layout, so hide its label explicitly.
        self.wiredForm.itemAt(1, QFormLayout.LabelRole).widget().setVisible(v208)
        self.wiredCard.setVisible(not self.wireless)
        self.wirelessCard.setVisible(self.wireless)
        if self.wireless:
            hint = ("V208：选择 .ota 包；安装后自动重连，核对运行版本、长度和 CRC32。" if v208 else
                    "G474：选择从 0x08000000 链接的 BIN，最大 128 KiB；需要支持 G474 下载的 Link V3 固件。目标擦写后读回校验。")
        else:
            hint = ("V208：使用 WCH-Link，支持 HEX / BIN。HEX 按内置地址烧录；首次安装或更新 Boot 请选择完整 factory 镜像。" if v208 else
                    "G474：使用 UF4 DAPLINK，支持 HEX / BIN，BIN 从 0x08000000 烧录，最大 128 KiB。请先关闭其他调试会话。")
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
        idle = not self._active and not self.home._busy and not self.home._closing
        self.connectionLabel.setText(self.home.connectionLabel.text() + " · " + self.home.versionLabel.text())
        for widget in (self.targetCombo, self.modeCombo, self.fileButton, self.toolEdit, self.toolButton,
                       self.configEdit, self.configButton, self.serialEdit, self.baseCombo):
            widget.setEnabled(idle)
        ready = bool(self._firmware)
        if self.wireless:
            ready = ready and self.home._connected and self.home._flash_ready and self.controller.loop is not None
        else:
            ready = ready and bool(self.toolEdit.text().strip()) and (self.target != V208 or bool(self.configEdit.text().strip()))
        self.startButton.setEnabled(idle and ready)
        self.cancelButton.setEnabled(self._active and self.wireless and self._can_cancel)

    def _tool(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 OpenOCD", self.toolEdit.text(), "OpenOCD (openocd.exe);;所有文件 (*)")
        if path:
            self.toolEdit.setText(path)
            config = Path(path).with_name("wch-riscv.cfg")
            if self.target == V208 and config.is_file():
                self.configEdit.setText(str(config))

    def _config(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 WCH 配置", self.configEdit.text(), "OpenOCD 配置 (*.cfg)")
        if path:
            self.configEdit.setText(path)

    def _load(self, path):
        return load_firmware(path, self.target, WIRELESS if self.wireless else WIRED, self.baseCombo.currentData())

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
            command = None
            if not self.wireless:
                self._temporary = tempfile.TemporaryDirectory(prefix="f4cp-flash-")
                snapshot = Path(self._temporary.name) / ("firmware" + firmware.suffix)
                snapshot.write_bytes(firmware.data)
                command = openocd_command(self.toolEdit.text().strip(), self.target, snapshot,
                                          self.baseCombo.currentData(), self.configEdit.text().strip(), self.serialEdit.text())
            warning = ("开始上传并安装？" if self.target == V208 and self.wireless else
                       "将擦写所选芯片的固件区域。擦写期间请保持供电和连接，完成前不能退出。是否开始？")
            if QMessageBox.question(self, "确认固件下载", self.targetCombo.currentText() + "\n" + self.modeCombo.currentText() + "\n" + firmware.summary + "\n\n" + warning) != QMessageBox.Yes:
                self._cleanup()
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
                self.home._external_busy = True
                self.home._sync()
                self._verified = False
                self._output_tail = ""
                self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
                self.process.setWorkingDirectory(str(Path(command[0]).parent))
                self.progressBar.setRange(0, 0)
                self.progressLabel.setText("正在有线烧录与校验，请保持连接…")
                self.process.start(*command)
        except Exception as exc:
            self._finish(False, str(exc))
        self._sync()

    def _output(self):
        text = self._decoder.decode(bytes(self.process.readAllStandardOutput()))
        self._verified = self._verified or "F4CP_VERIFY_OK" in self._output_tail + text
        self._output_tail = (self._output_tail + text)[-64:]
        self.log.moveCursor(self.log.textCursor().End)
        self.log.insertPlainText(text)

    def _wired_finished(self, code, status):
        if self._active and not self.wireless:
            self._output()
            success = code == 0 and status == QProcess.NormalExit and self._verified
            self._finish(success, "有线下载完成，OpenOCD 写入及读回校验通过" if success else f"有线下载未完成（退出码 {code}），请查看日志；未确认烧录成功")

    def _process_error(self, error):
        if error == QProcess.FailedToStart and self._active:
            self._finish(False, "无法启动 OpenOCD：" + self.process.errorString())

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

    def _cleanup(self):
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None

    def _finish(self, success, text):
        self._active = self._can_cancel = False
        self.home._external_busy = False
        self.home._sync()
        self._cleanup()
        self.progressBar.setRange(0, 100)
        if success:
            self.progressBar.setValue(100)
        self.progressLabel.setText(text)
        self.log.append(text)
        self._notify(success, text)
        self._sync()

    def _notify(self, success, text):
        (InfoBar.success if success else InfoBar.error)("下载完成" if success else "操作未完成", text, duration=6000, parent=self)
