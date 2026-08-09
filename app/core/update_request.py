# -*- coding: utf-8 -*-
from __future__ import annotations

from urllib.request import Request


def build_request(url: str, headers: dict[str, str] | None = None) -> Request:
    return Request(url, headers=headers or {})
