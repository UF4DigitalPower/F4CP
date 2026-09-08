# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from types import SimpleNamespace
import socket
import threading

from PyQt5.QtCore import QCoreApplication, QObject, QEvent


class SerialEventType(Enum):
    RX = auto()
    TX = auto()
    ERROR = auto()
    STATE = auto()


class SerialState(Enum):
    CLOSED = auto()
    OPEN = auto()


@dataclass(frozen=True)
class SerialConfig:
    port: str = ""
    baudrate: int = 115200


@dataclass(frozen=True)
class TcpConfig:
    host: str = ""
    port: int = 4884


class _SessionEvent(QEvent):
    def __init__(self, event_type: SerialEventType, payload=None):
        super().__init__(QEvent.Type.User)
        self._event_type = event_type
        self.payload = payload or SimpleNamespace()

    def type(self):
        return self._event_type


class RxEvent(_SessionEvent):
    def __init__(self, data: bytes = b""):
        super().__init__(SerialEventType.RX, SimpleNamespace(data=data))


class TxEvent(_SessionEvent):
    def __init__(self, data: bytes = b""):
        super().__init__(SerialEventType.TX, SimpleNamespace(data=data))


class ErrorEvent(_SessionEvent):
    def __init__(self, message: str = "逻辑层已移除"):
        super().__init__(SerialEventType.ERROR, SimpleNamespace(message=message))


class StateEvent(_SessionEvent):
    def __init__(self, state: SerialState = SerialState.CLOSED, info: str = ""):
        super().__init__(SerialEventType.STATE, SimpleNamespace(state=state, info=info))


class SendEvent(QEvent):
    def __init__(self, data: bytes = b""):
        super().__init__(QEvent.Type.User)
        self.data = data


class SerialSession(QObject):
    def __init__(self, config: SerialConfig | None = None, _event_receiver=None, parent=None):
        super().__init__(parent)
        self.config = config or SerialConfig()
        self.cfg = self.config
        self._event_receiver = _event_receiver
        self._serial = None
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._write_lock = threading.Lock()
        self.is_open = False

    def set_event_receiver(self, receiver) -> None:
        self._event_receiver = receiver

    def _post(self, event) -> None:
        if self._event_receiver is not None:
            QCoreApplication.postEvent(self._event_receiver, event)

    def open(self):
        if self.is_open:
            return True
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("缺少 pyserial，无法打开串口") from exc

        port = self.config.port.strip()
        if not port:
            raise ValueError("串口不能为空")
        self._serial = serial.Serial(
            port=port,
            baudrate=self.config.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.2,
            write_timeout=1.0,
        )
        self._stop.clear()
        self.is_open = True
        self._reader = threading.Thread(target=self._read_loop, name="uf4-serial-rx", daemon=True)
        self._reader.start()
        self._post(StateEvent(SerialState.OPEN, f"已打开串口: {port} @ {self.config.baudrate} 8N1"))
        return True

    def close(self):
        self._stop.set()
        serial_port, self._serial = self._serial, None
        self.is_open = False
        if serial_port is not None:
            serial_port.close()

    def write(self, data: bytes) -> int:
        if not self.is_open or self._serial is None:
            raise ConnectionError("串口未连接")
        with self._write_lock:
            count = self._serial.write(data)
            self._serial.flush()
        self._post(TxEvent(data[:count]))
        return count

    def _read_loop(self) -> None:
        try:
            while not self._stop.is_set() and self._serial is not None:
                data = self._serial.read(2048)
                if data:
                    self._post(RxEvent(data))
        except Exception as exc:
            if not self._stop.is_set():
                self._post(ErrorEvent(str(exc)))
        finally:
            was_open = self.is_open
            self.is_open = False
            if was_open:
                self._post(StateEvent(SerialState.CLOSED, "串口已断开"))


class PowerBluetoothSession(SerialSession):
    def __init__(self, name: str = "", address: str = "", parent=None):
        super().__init__(SerialConfig(port=address), parent=parent)
        self.name = name
        self.address = address


class TcpSession(QObject):
    """TCP byte-stream transport for the ESP32 UF4COM V4 bridge."""

    def __init__(self, config: TcpConfig, _event_receiver=None, parent=None):
        super().__init__(parent)
        self.config = config
        self._event_receiver = _event_receiver
        self._socket: socket.socket | None = None
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._write_lock = threading.Lock()
        self.is_open = False

    def set_event_receiver(self, receiver) -> None:
        self._event_receiver = receiver

    def _post(self, event) -> None:
        if self._event_receiver is not None:
            QCoreApplication.postEvent(self._event_receiver, event)

    def open(self):
        if self.is_open:
            return True
        self._stop.clear()
        sock = socket.create_connection((self.config.host, self.config.port), timeout=5.0)
        sock.settimeout(0.5)
        self._socket = sock
        self.is_open = True
        self._reader = threading.Thread(target=self._read_loop, name="uf4-tcp-rx", daemon=True)
        self._reader.start()
        self._post(StateEvent(SerialState.OPEN, f"已连接 Wi-Fi: {self.config.host}:{self.config.port}"))
        return True

    def close(self):
        self._stop.set()
        sock, self._socket = self._socket, None
        self.is_open = False
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    def write(self, data: bytes) -> int:
        if not self.is_open or self._socket is None:
            raise ConnectionError("Wi-Fi TCP 未连接")
        with self._write_lock:
            self._socket.sendall(data)
        self._post(TxEvent(data))
        return len(data)

    def _read_loop(self) -> None:
        try:
            while not self._stop.is_set() and self._socket is not None:
                try:
                    data = self._socket.recv(2048)
                except socket.timeout:
                    continue
                if not data:
                    raise ConnectionError("ESP32 已关闭 TCP 连接")
                self._post(RxEvent(data))
        except Exception as exc:
            if not self._stop.is_set():
                self._post(ErrorEvent(str(exc)))
        finally:
            was_open = self.is_open
            self.is_open = False
            if was_open:
                self._post(StateEvent(SerialState.CLOSED, "Wi-Fi TCP 已断开"))
