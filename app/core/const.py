# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class PowerCommand(IntEnum):
    READ = 0x01
    WRITE = 0x02
    STREAM_START = 0x10
    STREAM_STOP = 0x11
    STREAM_DATA = 0x15


class PowerDataType(IntEnum):
    SET_VOLTAGE_LIMIT = 17
    SET_CURRENT_LIMIT = 18
    POWER_STATE = 21
    FAULT_STATE = 22
    ADP_VOLTAGE_ERROR = 0x28
    LOOP_CURRENT_REFERENCE = 0x2A
    ADP_ACTION = 0x2C
    ADP_APPLIED_ACTION = 0x2D
    ADP_CRITIC_Q = 0x2E
    ADP_TD_ERROR = 0x2F


class PowerFrameFlag(IntEnum):
    ACK_REQ = 0x01
    ACK_FRAME = 0x02
    ERROR = 0x04


@dataclass(frozen=True)
class PowerDataMeta:
    type_id: PowerDataType
    unit: str
    label: str


POWER_DATA_META = {
    PowerDataType.SET_VOLTAGE_LIMIT: PowerDataMeta(PowerDataType.SET_VOLTAGE_LIMIT, "0.01 V", "Set Voltage Limit"),
    PowerDataType.SET_CURRENT_LIMIT: PowerDataMeta(PowerDataType.SET_CURRENT_LIMIT, "0.01 A", "Set Current Limit"),
    PowerDataType.POWER_STATE: PowerDataMeta(PowerDataType.POWER_STATE, "bool", "Power State"),
    PowerDataType.FAULT_STATE: PowerDataMeta(PowerDataType.FAULT_STATE, "bitmask", "Fault State"),
}
