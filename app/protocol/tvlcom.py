# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TvlcomTlvItem:
    type_id: int
    value: int | bytes | None = None


class TvlcomFrameParser:
    def feed(self, data: bytes):
        return []


def build_frame(command: int, sequence: int, payload: bytes = b"", flags: int = 0) -> bytes:
    return b""


def encode_tlv(type_id: int, value) -> bytes:
    return b""


def iter_tlv_items(payload: bytes, strict: bool = True):
    return iter(())
