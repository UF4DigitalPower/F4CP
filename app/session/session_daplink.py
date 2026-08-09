# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from PyQt5.QtCore import QObject, QEvent


class DaplinkProgrammerEventType(IntEnum):
    LOG = 1
    MESSAGE = 2
    STATE = 3
    PROBES = 4
    TARGETS = 5
    DEVICE_INFO = 6
    PROGRESS = 7
    ACTION_FINISHED = 8


@dataclass(frozen=True)
class DaplinkProbeInfo:
    uid: str = ""
    description: str = ""
    product_name: str = ""
    vendor_name: str = ""


@dataclass(frozen=True)
class DaplinkTargetInfo:
    target_id: str = ""
    part_number: str = ""
    flash_start: str = "--"
    flash_size: str = "--"
    ram_size: str = "--"
    pack_name: str = ""
    pack_version: str = ""


@dataclass(frozen=True)
class DaplinkDeviceInfo:
    probe_uid: str = "--"
    probe_description: str = "--"
    part_number: str = "--"
    flash_size: str = "--"
    pack_name: str = "--"
    pack_version: str = "--"


@dataclass(frozen=True)
class DaplinkConnectConfig:
    probe_uid: str | None = None
    target: str = ""
    pack: str = ""


@dataclass(frozen=True)
class DaplinkRequestPayload:
    action: str = ""
    connect_config: DaplinkConnectConfig | None = None
    file_path: str = ""
    base_address: str = ""
    erase_mode: str = ""
    smart_flash: bool = True
    silent: bool = False


@dataclass(frozen=True)
class ActionFinishedPayload:
    action: str = ""
    success: bool = False
    message: str = "DAPLink 逻辑已移除。"


class DaplinkRequestEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, payload: DaplinkRequestPayload):
        super().__init__(self.EVENT_TYPE)
        self.payload = payload


class DaplinkPyocdSession(QObject):
    def __init__(self, _event_receiver=None, parent=None):
        super().__init__(parent)
        self._event_receiver = _event_receiver

    def customEvent(self, event):
        pass
