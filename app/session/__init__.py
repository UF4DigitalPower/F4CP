# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from types import SimpleNamespace

from PyQt5.QtCore import QObject, QEvent, pyqtSlot


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


def listSerialPorts() -> list[str]:
    return []


@dataclass(frozen=True)
class PowerStatus:
    vin_v: float = 0.0
    iin_a: float = 0.0
    pin_w: float = 0.0
    vout_v: float = 0.0
    iout_a: float = 0.0
    pout_w: float = 0.0
    efficiency: float = 0.0
    core_temp_c: float = 0.0
    board_temp_c: float = 0.0
    set_voltage_limit_mv: int = 0
    set_current_limit_ma: int = 0
    ovp_set_value_v: float = 0.0
    ocp_set_value_a: float = 0.0
    otp_set_value_c: float = 0.0
    fan_set_value: int = 0
    fan_speed: int = 0
    power_enabled: bool = False
    power_state: int = 0
    fault_state: int = 0
    state_machine_flag_bits: int = 0
    mode_name: str = "未连接"
    topology_name: str = "未连接"
    state_flag_name: str = "IDLE"
    pwm_a_compare: int = 0
    pwm_d_compare: int = 0
    ovp_set_value_mv: int = 0
    ocp_set_value_ma: int = 0
    otp_set_value_mc: int = 0


DEFAULT_STATUS_VALUES = PowerStatus().__dict__.copy()


def build_status(values: dict | None = None) -> PowerStatus:
    data = dict(DEFAULT_STATUS_VALUES)
    if values:
        data.update(values)
    return PowerStatus(**{key: data[key] for key in DEFAULT_STATUS_VALUES})


def pretty_faults(fault_state: int) -> str:
    return "无故障" if not fault_state else f"0x{fault_state:04X}"


class F4CPPowerClient(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_connected = False
        self.is_busy = False

    def pretty_print_status(self, status: PowerStatus) -> str:
        return "电源逻辑层已移除，当前为界面占位状态。"

    @pyqtSlot()
    def shutdown(self) -> None:
        self.is_connected = False
        self.is_busy = False
