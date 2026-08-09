# -*- coding: utf-8 -*-
# -------------------------------
#  @Project : F4CP
#  @Time    : 2026 - 01-08 12:30
#  @FileName: session_bluetooth.py
#  @FileType: 蓝牙会话文件，负责蓝牙通道的占位和扩展
#  @Software: PyCharm 2024.1.6 (Professional Edition)
#  @System  : Windows 11 23H2
#  @Author  : UF4
#  @Contact :
#  @Python  : 3.10
# -------------------------------

from types import SimpleNamespace

from PyQt5.QtBluetooth import (
    QBluetoothAddress,
    QBluetoothUuid,
    QLowEnergyCharacteristic,
    QLowEnergyController,
    QLowEnergyDescriptor,
    QLowEnergyService,
)
from PyQt5.QtCore import QObject, QCoreApplication, QByteArray

from config import get_logger
from .session_serial import SerialState, StateEvent,TxEvent, SerialEventType, ErrorEvent, RxEvent

logger = get_logger("BluetoothSession")

UART_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_RX_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"


class PowerBluetoothSession(QObject):
    def __init__(self, name: str, address: str, parent=None):
        super().__init__(parent)
        self.name = name
        self.address = address
        self.device_info = None
        self.cfg = SimpleNamespace(port=name)
        self._eventReceiver = None
        self._controller = None
        self._service = None
        self._rxCharacteristic = QLowEnergyCharacteristic()
        self._txCharacteristic = QLowEnergyCharacteristic()

    def set_event_receiver(self, receiver) -> None:
        self._eventReceiver = receiver

    @property
    def is_open(self) -> bool:
        return bool(self._service) and self._rxCharacteristic.isValid()

    def open(self) -> None:
        if self.is_open:
            return
        if (
            QBluetoothAddress is None
            or QBluetoothUuid is None
            or QLowEnergyController is None
            or QLowEnergyService is None
        ):
            message = "当前环境不支持 Qt Bluetooth"
            logger.error(message)
            raise RuntimeError(message)

        self._postEvent(StateEvent(SerialState.OPENING))
        if self.device_info is not None:
            self._controller = QLowEnergyController.createCentral(self.device_info, self)
        else:
            self._controller = QLowEnergyController.createCentral(
                QBluetoothAddress(self.address),
                QBluetoothAddress(),
                self,
            )
        self._controller.connected.connect(self._onControllerConnected)
        self._controller.disconnected.connect(lambda: self._postEvent(StateEvent(SerialState.CLOSED)))
        self._controller.serviceDiscovered.connect(self._onServiceDiscovered)
        self._controller.discoveryFinished.connect(self._onDiscoveryFinished)
        self._controller.error.connect(self._onControllerError)
        self._controller.connectToDevice()

    def close(self) -> None:
        if self._controller:
            self._controller.disconnectFromDevice()
            self._controller.deleteLater()
        if self._service:
            self._service.deleteLater()
        self._controller = None
        self._service = None
        self._rxCharacteristic = QLowEnergyCharacteristic()
        self._txCharacteristic = QLowEnergyCharacteristic()
        self._postEvent(StateEvent(SerialState.CLOSED))

    def write(self, data: bytes) -> int:
        if not self.is_open:
            message = "蓝牙设备未连接"
            logger.error(message)
            raise RuntimeError(message)
        self._service.writeCharacteristic(
            self._rxCharacteristic,
            QByteArray(data),
            QLowEnergyService.WriteWithoutResponse,
        )
        self._postEvent(TxEvent(data))
        return len(data)

    def event(self, event) -> bool:
        if event.type() == int(SerialEventType.SEND):
            payload = getattr(event, "payload", None)
            data = getattr(payload, "data", b"") if payload is not None else b""
            if data:
                try:
                    self.write(data)
                except Exception as exc:
                    self._postEvent(ErrorEvent(code=-1, message=str(exc), fatal=False))
            return True
        return super().event(event)

    def _postEvent(self, event) -> None:
        if self._eventReceiver is not None:
            QCoreApplication.postEvent(self._eventReceiver, event)

    def _onControllerConnected(self) -> None:
        if self._controller:
            self._controller.discoverServices()

    def _onServiceDiscovered(self, uuid) -> None:
        if uuid == QBluetoothUuid(UART_SERVICE_UUID):
            logger.info(f"发现 BLE UART 服务: {uuid.toString()}")

    def _onDiscoveryFinished(self) -> None:
        if not self._controller:
            return
        self._service = self._controller.createServiceObject(QBluetoothUuid(UART_SERVICE_UUID), self)
        if not self._service:
            self._postEvent(ErrorEvent(code=-1, message="未发现 BLE UART 服务", fatal=True))
            self._postEvent(StateEvent(SerialState.ERROR, info="未发现 BLE UART 服务"))
            return
        self._service.stateChanged.connect(self._onServiceStateChanged)
        self._service.characteristicChanged.connect(self._onCharacteristicChanged)
        self._service.error.connect(self._onServiceError)
        self._service.discoverDetails()

    def _onServiceStateChanged(self, state) -> None:
        if state != QLowEnergyService.ServiceDiscovered or not self._service:
            return
        self._txCharacteristic = self._service.characteristic(QBluetoothUuid(UART_TX_UUID))
        self._rxCharacteristic = self._service.characteristic(QBluetoothUuid(UART_RX_UUID))
        if not self._txCharacteristic.isValid() or not self._rxCharacteristic.isValid():
            message = "BLE UART 特征不完整"
            self._postEvent(ErrorEvent(code=-1, message=message, fatal=True))
            self._postEvent(StateEvent(SerialState.ERROR, info=message))
            return
        cccd = self._txCharacteristic.descriptor(QBluetoothUuid(QBluetoothUuid.DescriptorType.ClientCharacteristicConfiguration))
        if cccd.isValid():
            self._service.writeDescriptor(cccd, QByteArray(b"\x01\x00"))
        self._postEvent(StateEvent(SerialState.OPEN))

    def _onCharacteristicChanged(self, characteristic, value) -> None:
        if characteristic.uuid() != QBluetoothUuid(UART_TX_UUID):
            return
        data = bytes(value)
        if data:
            self._postEvent(RxEvent(data))

    def _onControllerError(self, error) -> None:
        message = self._controller.errorString() if self._controller else str(error)
        self._postEvent(ErrorEvent(code=int(error), message=message, fatal=True))
        self._postEvent(StateEvent(SerialState.ERROR, info=message))

    def _onServiceError(self, error) -> None:
        message = self._service.errorString() if self._service and hasattr(self._service, "errorString") else str(error)
        self._postEvent(ErrorEvent(code=int(error), message=message, fatal=True))
        self._postEvent(StateEvent(SerialState.ERROR, info=message))
