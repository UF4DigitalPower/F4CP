# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Sample:
    t: float
    value: float

    @property
    def timestamp(self) -> float:
        return self.t
