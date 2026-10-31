# -*- coding: utf-8 -*-
# -------------------------------
#  @Project : F4CP
#  @Time    : 2026 - 01-08 12:30
#  @FileName: storage.py
#  @FileType: 配置存储模块，负责 JSON 读写、旧配置迁移和原子保存
#  @Software: PyCharm 2024.1.6 (Professional Edition)
#  @System  : Windows 11 23H2
#  @Author  : UF4
#  @Contact :
#  @Python  : 3.11
# -------------------------------

"""Strict JSON reads, compatible migrations, and atomic configuration writes."""
from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path

from .constants import (
    APP_REPOSITORY_URL, LEGACY_APP_REPOSITORY_URL, UPDATE_SECTION,
    VERSION_CURRENT_SECTION, VERSION_LATEST_SECTION,
)


class ConfigLoadError(ValueError):
    pass


class JsonConfigStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            with self.path.open(encoding="utf-8-sig") as source:
                data = json.load(source)
        except (ValueError, UnicodeError) as exc:
            raise ConfigLoadError(f"配置文件格式无效：{self.path}（{exc}）") from exc
        if not isinstance(data, dict):
            raise ConfigLoadError(f"配置文件的根节点必须是 JSON 对象：{self.path}")
        return data

    def write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", prefix=".f4cp-config-", suffix=".tmp",
                dir=self.path.parent, delete=False,
            ) as output:
                temporary = Path(output.name)
                json.dump(data, output, ensure_ascii=False, indent=4)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def migrate_config(data: dict) -> dict:
    """Migrate former defaults only; preserve custom URLs, firmware and unknown keys."""
    data = deepcopy(data)
    for legacy_group, target_group, mappings in (
        ("OldVersion", VERSION_CURRENT_SECTION,
         {"OldLocalVersion": "App", "OldLowerVersion": "Power", "OldUpperVersion": "Upper"}),
        ("NewVersion", VERSION_LATEST_SECTION,
         {"NewLocalVersion": "App", "NewLowerVersion": "Power", "NewUpperVersion": "Upper"}),
    ):
        section = data.get(legacy_group)
        if not isinstance(section, dict):
            continue
        current = data.setdefault(target_group, {})
        if not isinstance(current, dict):
            continue
        # Application.Version was previously the displayed/running software version.
        application = data.get("Application", {})
        if target_group == VERSION_CURRENT_SECTION and isinstance(application, dict) and "Version" in application:
            current.setdefault("App", application["Version"])
        for old_key, new_key in mappings.items():
            if old_key in section:
                current.setdefault(new_key, section.pop(old_key))
        if not section:
            del data[legacy_group]
    application = data.get("Application")
    if isinstance(application, dict) and "Version" in application:
        current = data.setdefault(VERSION_CURRENT_SECTION, {})
        if isinstance(current, dict):
            current.setdefault("App", application.pop("Version"))
    legacy_update = data.get("update")
    if isinstance(legacy_update, dict):
        current = data.get(UPDATE_SECTION)
        if current is None or isinstance(current, dict):
            data[UPDATE_SECTION] = {**legacy_update, **(current or {})}
            del data["update"]
    for group, key, suffix in (
        (UPDATE_SECTION, "UpdateUrl", "/releases"),
        ("Application", "RepoUrl", ""),
        ("Application", "ReleaseUrl", "/releases/latest"),
    ):
        section = data.get(group)
        if not isinstance(section, dict):
            continue
        value = section.get(key)
        if isinstance(value, str) and value.rstrip("/") == LEGACY_APP_REPOSITORY_URL + suffix:
            section[key] = APP_REPOSITORY_URL + suffix
    return data
