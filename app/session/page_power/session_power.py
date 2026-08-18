# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass

from PyQt5.QtCore import QObject, pyqtSlot


@dataclass(frozen=True)
class SerialConfig:
    port: str = ""
    baudrate: int = 115200


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

    def set_event_receiver(self, receiver) -> None:
        self._event_receiver = receiver


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
