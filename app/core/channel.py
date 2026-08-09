# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelConfig:
    key: str
    name: str
    unit: str
    precision: int = 2
    group: str = ""
    color: tuple[int, int, int] = (80, 120, 200)
    line_width: float = 1.5
