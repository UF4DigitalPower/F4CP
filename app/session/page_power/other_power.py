# -*- coding: utf-8 -*-
from __future__ import annotations

from app.session.page_power.session_power import PowerStatus


DEFAULT_STATUS_VALUES = PowerStatus().__dict__.copy()


def build_status(values: dict | None = None) -> PowerStatus:
    data = dict(DEFAULT_STATUS_VALUES)
    if values:
        data.update(values)
    return PowerStatus(**{key: data[key] for key in DEFAULT_STATUS_VALUES})


def listSerialPorts() -> list[str]:
    try:
        from serial.tools import list_ports
        return sorted(
            {port.device for port in list_ports.comports() if port.device},
            key=lambda value: (value.upper().startswith("COM"), value.upper()),
        )
    except Exception:
        return []


def pretty_faults(fault_state: int) -> str:
    return "无故障" if not fault_state else f"0x{fault_state:04X}"
