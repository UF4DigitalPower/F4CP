# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.core.channel import ChannelConfig
from app.core.ring_buffer import Sample


@dataclass
class ChannelBuffer:
    config: ChannelConfig
    samples: list[Sample] = field(default_factory=list)

    @property
    def key(self) -> str:
        return self.config.key

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def unit(self) -> str:
        return self.config.unit

    @property
    def precision(self) -> int:
        return self.config.precision

    @property
    def color(self) -> tuple[int, int, int]:
        return self.config.color

    @property
    def line_width(self) -> float:
        return self.config.line_width

    def append(self, timestamp: float, value: float) -> None:
        self.samples.append(Sample(timestamp, value))

    def window(self, seconds: float, now: float) -> list[Sample]:
        start = now - seconds
        return [sample for sample in self.samples if start <= sample.t <= now]

    def snapshot(self) -> list[Sample]:
        return list(self.samples)

    def clear(self) -> None:
        self.samples.clear()


class DataHub:
    def __init__(self, default_max_points: int = 6000):
        self.default_max_points = default_max_points
        self._channels: dict[str, ChannelBuffer] = {}

    def register_channels(self, configs, max_points: int | None = None) -> None:
        for config in configs:
            self._channels[config.key] = ChannelBuffer(config=config)

    def channel(self, key: str) -> ChannelBuffer | None:
        return self._channels.get(key)

    def get_channel(self, key: str) -> ChannelBuffer | None:
        return self.channel(key)

    def channels(self) -> list[ChannelBuffer]:
        return list(self._channels.values())

    def visible_channels(self) -> list[ChannelBuffer]:
        return self.channels()

    def append(self, key: str, timestamp: float, value: float) -> None:
        if key in self._channels:
            self._channels[key].append(timestamp, value)

    def append_many(self, timestamp: float, values: dict[str, float]) -> None:
        for key, value in values.items():
            self.append(key, timestamp, value)

    def push(self, key: str, value: float, t: float | None = None) -> None:
        """追加单个采样点（t 缺省时取当前时间）。"""
        self.append(key, time.time() if t is None else t, value)

    def push_many(self, values: dict[str, float], t: float | None = None) -> None:
        """批量追加采样点（t 缺省时取当前时间）。"""
        timestamp = time.time() if t is None else t
        for key, value in values.items():
            self.append(key, timestamp, value)

    def clear(self) -> None:
        for channel in self._channels.values():
            channel.clear()
