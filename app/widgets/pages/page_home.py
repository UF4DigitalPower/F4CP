"""Device connection, communication and firmware OTA workspace."""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, ComboBox, InfoBar,
    LineEdit, PrimaryPushButton, PushButton, ScrollArea, SubtitleLabel, TextEdit)
from app.protocol.ble_device import FLASH_UNAVAILABLE, decode_device_info
from app.session.ble_controller import BleController
from app.widgets.components import PageHeader
from config import CTX


def section(parent, title, subtitle):
    card = CardWidget(parent)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)
    layout.addWidget(SubtitleLabel(title, card))
    caption = CaptionLabel(subtitle, card)
    caption.setWordWrap(True)
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
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(12)
    layout.addWidget(PageHeader(title, subtitle, content))
    return content, layout


class HomePage(ScrollArea):
    stateChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        content, layout = page_content(self, "HomePage", "设备工作台", "连接 UF4 Power，管理设备通信；固件升级请前往固件下载页。")
        self._connected = self._busy = self._external_busy = self._closing = False
        self._flash_ready = False
        card, body = section(content, "设备连接", "设备配对码为 005213，软件自动提交口令；若系统弹出提示，请按提示确认。")
        self.deviceCombo = ComboBox(card)
        self.deviceCombo.setMinimumWidth(320)
        self.scanButton = PushButton("扫描设备", card)
        self.connectButton = PrimaryPushButton("连接", card)
        self.disconnectButton = PushButton("断开", card)
        self.repairButton = PushButton("重新配对", card)
        self.repairButton.setToolTip("清除所选设备在电脑上的绑定，再重新配对；用于刷机后认证失败")
        row = QHBoxLayout()
        for w in (self.deviceCombo, self.scanButton, self.connectButton, self.disconnectButton, self.repairButton): row.addWidget(w)
        body.addLayout(row)
        self.connectionLabel = BodyLabel("未连接", card)
        self.versionLabel = CaptionLabel("设备版本：--", card)
        body.addWidget(self.connectionLabel)
        body.addWidget(self.versionLabel)
        layout.addWidget(card)
        card, body = section(content, "固件下载", "V208 / G474 的有线下载与无线升级已集中到独立页面。")
        self.firmwareButton = PushButton("打开固件下载", card)
        self.firmwareButton.clicked.connect(lambda: self.window().switchTo(self.window().firmwareInterface))
        body.addWidget(self.firmwareButton, 0, Qt.AlignLeft)
        layout.addWidget(card)
        card, body = section(content, "设备通信", "读取设备与外部存储信息，或发送十六进制命令进行通信调试。")
        row = QHBoxLayout()
        self.commandEdit = LineEdit(card)
        self.commandEdit.setPlaceholderText("例如：01 55 AA（回显）或 00（设备信息）")
        self.infoButton = PushButton("读取设备信息", card)
        self.usbButton = PushButton("USB诊断", card)
        self.sendButton = PushButton("发送", card)
        row.addWidget(self.commandEdit, 1)
        row.addWidget(self.infoButton)
        row.addWidget(self.usbButton)
        row.addWidget(self.sendButton)
        body.addLayout(row)
        self.storageLabel = CaptionLabel("W25Q256：等待设备信息", card)
        self.storageLabel.setWordWrap(True)
        self.log = TextEdit(card)
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(150)
        self.log.document().setMaximumBlockCount(500)
        body.addWidget(self.storageLabel)
        body.addWidget(self.log)
        layout.addWidget(card)
        layout.addStretch()
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
        self._sync()

    def _connect(self):
        address = self.deviceCombo.currentData()
        if address: self.controller.submit("connect", address)

    def _connection(self, connected):
        self._connected = connected
        self.connectionLabel.setText("已连接 · 安全链路" if connected else "未连接")
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
        if self._connected:
            try: CTX.versions.set_current("Upper", version.split(" · ")[0])
            except Exception as exc: self._message(f"版本缓存保存失败：{exc}")

    def _set_busy(self, busy):
        self._busy = busy
        self._sync()

    def _message(self, message): self.log.append(message)

    def _received(self, raw):
        self._message("RX  " + raw.hex(" ").upper())
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
            if self.controller.submit("exchange", payload): self._message("TX  " + payload.hex(" ").upper())
        except ValueError as exc: self._result(False, str(exc))

    def _result(self, success, text):
        self._message(text)
        firmware = getattr(self.window(), "firmwareInterface", None)
        if firmware is not None and firmware._active:
            return
        if not self._closing:
            (InfoBar.success if success else InfoBar.error)("操作成功" if success else "操作未完成", text, duration=6000, parent=self)

    def shutdown(self):
        self._closing = True
        return self.controller.shutdown()
