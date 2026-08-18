# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from types import SimpleNamespace

from PyQt5.QtCore import QObject, QEvent


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
        self.is_open = False

    def open(self):
        self.is_open = False
        return False

    def close(self):
        self.is_open = False

    def write(self, data: bytes) -> int:
        return 0


class PowerBluetoothSession(SerialSession):
    def __init__(self, name: str = "", address: str = "", parent=None):
        super().__init__(SerialConfig(port=address), parent=parent)
        self.name = name
        self.address = address
