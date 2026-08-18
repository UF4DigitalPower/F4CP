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
    return []


def pretty_faults(fault_state: int) -> str:
    return "无故障" if not fault_state else f"0x{fault_state:04X}"
