# -*- coding: utf-8 -*-
# -------------------------------
#  @Project : F4CP
#  @Time    : 2026 - 10-31
#  @FileName: version.py
#  @FileType: 版本模型，统一版本比较、状态快照和运行软件版本解析
#  @Software: PyCharm 2024.1.6 (Professional Edition)
#  @System  : Windows 11 23H2
#  @Author  : UF4
#  @Contact :
#  @Python  : 3.11
# -------------------------------

"""Shared version rules and immutable snapshots, independent of Qt and storage."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from enum import Enum
from importlib.metadata import PackageNotFoundError, version as distribution_version
from pathlib import Path

from packaging.version import InvalidVersion, Version


class VersionError(ValueError):
    pass


class VersionComponent(str, Enum):
    APP = "App"
    POWER = "Power"
    UPPER = "Upper"


class VersionState(str, Enum):
    UNKNOWN = "unknown"
    INVALID = "invalid"
    CURRENT = "current"
    UPDATE_AVAILABLE = "update_available"
    AHEAD = "ahead"


def parse_version(value: str) -> Version:
    if not isinstance(value, str):
        raise VersionError("版本号必须是字符串。")
    try:
        return Version(value.strip())
    except InvalidVersion as exc:
        raise VersionError(f"无法识别版本号：{value}。请使用 v2.0.0、2.0.0.A1 或 2.0.0.RC1 等格式。") from exc


def is_newer_version(remote: str, local: str) -> bool:
    return parse_version(remote) > parse_version(local)


@dataclass(frozen=True)
class VersionPair:
    current: str = ""
    latest: str = ""

    @property
    def state(self) -> VersionState:
        if not self.current or not self.latest:
            return VersionState.UNKNOWN
        try:
            current, latest = parse_version(self.current), parse_version(self.latest)
        except VersionError:
            return VersionState.INVALID
        if latest > current:
            return VersionState.UPDATE_AVAILABLE
        if latest < current:
            return VersionState.AHEAD
        return VersionState.CURRENT

    @property
    def has_update(self) -> bool:
        return self.state == VersionState.UPDATE_AVAILABLE

    @property
    def message(self) -> str:
        return {
            VersionState.UNKNOWN: "版本信息不完整，暂时无法判断是否需要更新。",
            VersionState.INVALID: "版本号格式无效，暂时无法判断是否需要更新。",
            VersionState.CURRENT: "当前已是最新版本。",
            VersionState.UPDATE_AVAILABLE: f"发现新版本 {self.latest}。",
            VersionState.AHEAD: "当前版本高于最新发布版本，无需降级。",
        }[self.state]


@dataclass(frozen=True)
class VersionSnapshot:
    # Retain existing field names for event consumers and third-party integrations.
    local_app_version: str = ""
    latest_app_version: str = ""
    local_lower_version: str = ""
    latest_lower_version: str = ""
    local_upper_version: str = ""
    latest_upper_version: str = ""

    @property
    def app(self) -> VersionPair:
        return VersionPair(self.local_app_version, self.latest_app_version)

    @property
    def power(self) -> VersionPair:
        return VersionPair(self.local_lower_version, self.latest_lower_version)

    @property
    def upper(self) -> VersionPair:
        return VersionPair(self.local_upper_version, self.latest_upper_version)

    def get(self, component: VersionComponent | str) -> VersionPair:
        return getattr(self, VersionComponent(component).value.lower())

    def with_latest(self, component: VersionComponent | str, value: str) -> VersionSnapshot:
        field = {
            VersionComponent.APP: "latest_app_version",
            VersionComponent.POWER: "latest_lower_version",
            VersionComponent.UPPER: "latest_upper_version",
        }[VersionComponent(component)]
        return replace(self, **{field: value})


def application_version(base_dir: Path, fallback: str = "") -> str:
    """Prefer the source/shipped project metadata; support older packaged apps."""
    try:
        with (Path(base_dir) / "pyproject.toml").open("rb") as source:
            value = tomllib.load(source)["project"]["version"]
        parse_version(value)
        return value.strip()
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:
        value = distribution_version("F4CP")
        parse_version(value)
        return value
    except (PackageNotFoundError, VersionError):
        return fallback if isinstance(fallback, str) else ""
