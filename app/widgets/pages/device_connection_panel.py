"""Device connection, communication and firmware OTA workspace."""
import logging
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon as FIF, InfoBar,
    LineEdit, PrimaryPushButton, PushButton, TransparentPushButton)
from app.widgets.components.chip import ChipTone, StatusChip
from app.protocol.ble_device import FLASH_UNAVAILABLE, decode_device_info
from app.session.ble_controller import BleController
from .page_layout import section
from config import CTX

LOGGER = logging.getLogger("F4CP.Device")


class DeviceConnectionPanel(QWidget):
    stateChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        content = self
        self.setObjectName("DeviceConnectionPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self._connected = self._busy = self._external_busy = self._closing = False
        self._flash_ready = False
        card, body = section(content, "蓝牙设备", "配对码 005213 · 软件自动提交，按系统提示完成认证。", embedded=True)
        self.deviceCombo = ComboBox(card)
        self.deviceCombo.setMinimumWidth(0)
        self.deviceCombo.setPlaceholderText("扫描并选择 UF4 设备")
        self.scanButton = PushButton(FIF.SYNC, "扫描设备", card)
        self.connectButton = PrimaryPushButton(FIF.LINK, "连接", card)
        self.disconnectButton = PushButton("断开", card)
        self.repairButton = TransparentPushButton("重新配对", card)
        self.repairButton.setToolTip("清除所选设备在电脑上的绑定，再重新配对；用于刷机后认证失败")
        row = QHBoxLayout()
        body.addWidget(self.deviceCombo)
        for w in (self.scanButton, self.connectButton, self.disconnectButton): row.addWidget(w)
        row.addStretch()
        row.addWidget(self.repairButton)
        body.addLayout(row)
        self.connectionLabel = StatusChip("未连接", parent=card)
        self.versionLabel = CaptionLabel("设备版本：--", card)
        status_row = QHBoxLayout()
        status_row.addWidget(self.connectionLabel, 0, Qt.AlignLeft)
        status_row.addStretch()
        self.communicationButton = TransparentPushButton(FIF.CODE, "通信调试", card)
        status_row.addWidget(self.communicationButton)
        body.addLayout(status_row)
        body.addWidget(self.versionLabel)
        self.activityLabel = CaptionLabel("等待扫描设备", card)
        self.activityLabel.setWordWrap(True)
        body.addWidget(self.activityLabel)
        self.storageLabel = CaptionLabel("W25Q256：等待设备信息", card)
        self.storageLabel.setWordWrap(True)
        body.addWidget(self.storageLabel)
        layout.addWidget(card)
        card, body = section(content, "通信调试", "读取设备信息、发送十六进制命令；完整收发记录在运行日志中查看。")
        self.communicationCard = card
        card.setVisible(False)
        self.communicationButton.clicked.connect(self._toggle_communication)
        row = QHBoxLayout()
        self.commandEdit = LineEdit(card)
        self.commandEdit.setPlaceholderText("例如：01 55 AA（回显）或 00（设备信息）")
        self.infoButton = PushButton("读取设备信息", card)
        self.usbButton = PushButton("USB诊断", card)
        self.sendButton = PushButton("发送", card)
        body.addWidget(self.commandEdit)
        row.addWidget(self.infoButton)
        row.addWidget(self.usbButton)
        row.addWidget(self.sendButton)
        body.addLayout(row)
        self.responseLabel = CaptionLabel("尚未收发通信数据", card)
        self.responseLabel.setWordWrap(True)
        self.responseLabel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.addWidget(self.responseLabel)
        layout.addWidget(card)
        self.controller = BleController(self)
        for signal, slot in ((self.controller.devices, self._devices), (self.controller.connected, self._connection),
            (self.controller.version, self._version), (self.controller.message, self._message),
            (self.controller.received, self._received), (self.controller.busy, self._set_busy),
            (self.controller.result, self._result), (self.controller.ready, self._sync)):
            signal.connect(slot)
        self.scanButton.clicked.connect(lambda: self.controller.submit("scan"))
        self.connectButton.clicked.connect(self._connect)
        self.disconnectButton.clicked.connect(lambda: self.controller.submit("disconnect"))
        self.repairButton.clicked.connect(self._repair_pairing)
        self.infoButton.clicked.connect(lambda: self.controller.submit("exchange", b"\x00"))
        self.usbButton.clicked.connect(lambda: self.controller.submit("usb_diagnostics"))
        self.sendButton.clicked.connect(self._send)
        self.commandEdit.returnPressed.connect(self._send)
        self.controller.start()
        self._sync()

    def _toggle_communication(self):
        opened = self.communicationCard.isHidden()
        self.communicationCard.setVisible(opened)
        self.communicationButton.setText("收起通信调试" if opened else "通信调试")

    def _sync(self):
        idle = self.controller.isRunning() and self.controller.loop is not None and not self._busy and not self._external_busy and not self._closing
        self.scanButton.setEnabled(idle and not self._connected)
        self.deviceCombo.setEnabled(idle and not self._connected)
        self.connectButton.setEnabled(idle and not self._connected and self.deviceCombo.count() > 0)
        self.disconnectButton.setEnabled(idle and self._connected)
        self.repairButton.setEnabled(idle and not self._connected and self.deviceCombo.count() > 0)
        for w in (self.commandEdit, self.infoButton, self.usbButton, self.sendButton): w.setEnabled(idle and self._connected)
        self.stateChanged.emit()

    def _devices(self, devices):
        self.deviceCombo.clear()
        for name, address, rssi in devices:
            self.deviceCombo.addItem(f"{name} · {address} · {rssi} dBm", userData=address)
        self.activityLabel.setText(f"发现 {len(devices)} 台设备" if devices else "未发现设备，请确认设备已上电后重新扫描")
        self._sync()

    def _connect(self):
        address = self.deviceCombo.currentData()
        if address: self.controller.submit("connect", address)

    def _connection(self, connected):
        self._connected = connected
        self.connectionLabel.setText("已连接 · 安全链路" if connected else "未连接")
        self.connectionLabel.setTone(ChipTone.SUCCESS if connected else ChipTone.NEUTRAL)
        LOGGER.info("设备已连接，安全链路通过" if connected else "设备已断开")
        if not connected:
            self._flash_ready = False
            self.versionLabel.setText("设备版本：--")
            self.storageLabel.setText("W25Q256：等待设备信息")
        self._sync()

    def _repair_pairing(self):
        address = self.deviceCombo.currentData()
        if address:
            self.controller.submit("repair_pairing", address)

    def _version(self, version):
        self.versionLabel.setText("设备版本：" + version)
        LOGGER.info("设备版本：%s", version)
        if self._connected:
            try: CTX.versions.set_current("Upper", version.split(" · ")[0])
            except Exception as exc: self._message(f"版本缓存保存失败：{exc}")

    def _set_busy(self, busy):
        self._busy = busy
        self._sync()

    def _message(self, message):
        # TransferDiagnostics already writes these records to the shared logger.
        if message.startswith(("BLE 上传诊断 [", "BLE 上传耗时 [")):
            return
        LOGGER.info(message)
        if not self._external_busy and not getattr(self.parent(), "_active", False):
            self.activityLabel.setText(message if "\n" not in message else "诊断信息已生成，请查看运行日志")

    def _received(self, raw):
        received = "RX  " + raw.hex(" ").upper()
        LOGGER.info(received)
        self.responseLabel.setText(received)
        if len(raw) == 20 and raw[0] == 1 and raw[2:4] == b"\x00\x00":
            try:
                self._flash_ready, jedec, capacity, user_base = decode_device_info(raw)
            except ValueError as exc:
                self._flash_ready = False
                self.storageLabel.setText(str(exc))
            else:
                if self._flash_ready:
                    self.storageLabel.setText(f"W25Q256：已识别 · JEDEC {jedec:06X} · {capacity // 1024 // 1024} MiB · 用户数据区 {(capacity - user_base) // 1024 // 1024} MiB")
                else:
                    self.storageLabel.setText(FLASH_UNAVAILABLE)
                    self._message(FLASH_UNAVAILABLE)
            self._sync()

    def _send(self):
        try:
            payload = bytes.fromhex(self.commandEdit.text())
            if not 1 <= len(payload) <= 20: raise ValueError("请输入 1～20 字节的十六进制命令")
            if self.controller.submit("exchange", payload):
                text = "TX  " + payload.hex(" ").upper()
                LOGGER.info(text)
                self.responseLabel.setText(text)
        except ValueError as exc: self._result(False, str(exc))

    def _result(self, success, text):
        firmware = getattr(self.window(), "firmwareInterface", None)
        if firmware is not None and firmware._active:
            return
        (LOGGER.info if success else LOGGER.error)(text)
        self.activityLabel.setText(text)
        if not self._closing:
            (InfoBar.success if success else InfoBar.error)("操作成功" if success else "操作未完成", text,
                                                          duration=6000 if success else -1, parent=self)

    def shutdown(self):
        self._closing = True
        return self.controller.shutdown()
