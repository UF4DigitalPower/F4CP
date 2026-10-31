# -*- coding: utf-8 -*-
# -------------------------------
#  @Project : F4CP
#  @Time    : 2026 - 01-08 12:30
#  @FileName: schema.py
#  @FileType: 配置项定义模块，负责默认值、验证、实例隔离和主题绑定
#  @Software: PyCharm 2024.1.6 (Professional Edition)
#  @System  : Windows 11 23H2
#  @Author  : UF4
#  @Contact :
#  @Python  : 3.11
# -------------------------------

"""Typed Fluent configuration schema with independent items for each instance."""
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

from qfluentwidgets import BoolValidator, ColorConfigItem, ConfigItem, QConfig, qconfig

from . import constants as keys
from .logging import get_logger
from .storage import JsonConfigStore, migrate_config

_log = get_logger("Config")


def _is_win11() -> bool:
    return sys.platform == "win32" and sys.getwindowsversion().build >= 22000


class F4CPConfig(QConfig):
    """Keep Qt signals and JSON keys stable without sharing ConfigItem objects."""
    micaEnabled = ConfigItem("MainWindow", "MicaEnabled", _is_win11(), BoolValidator())
    highDpiScaling = ConfigItem("MainWindow", "HighDpiScaling", True, BoolValidator(), restart=True)

    checkUpdateAtStartUp = ConfigItem(keys.UPDATE_SECTION, "CheckUpdateAtStartUp", True, BoolValidator())
    updateUrl = ConfigItem(keys.UPDATE_SECTION, "UpdateUrl", keys.APP_REPOSITORY_URL + "/releases")
    includePrereleases = ConfigItem(keys.UPDATE_SECTION, "IncludePrereleases", False, BoolValidator())

    firmwareBaseUrl = ConfigItem(keys.FIRMWARE_REMOTE_SECTION, "BaseUrl", "")
    firmwareGithubOwner = ConfigItem(keys.FIRMWARE_REMOTE_SECTION, "GithubOwner", "UF4OVER")
    firmwareGithubRepo = ConfigItem(keys.FIRMWARE_REMOTE_SECTION, "GithubRepo", "UF4DigitalPower")
    githubSessionToken = ConfigItem("GithubAuth", "SessionToken", "")
    githubLogin = ConfigItem("GithubAuth", "Login", "")
    githubName = ConfigItem("GithubAuth", "Name", "")
    githubAvatarUrl = ConfigItem("GithubAuth", "AvatarUrl", "")
    githubProfileUrl = ConfigItem("GithubAuth", "ProfileUrl", "")
    githubSessionExpiresAt = ConfigItem("GithubAuth", "SessionExpiresAt", 0)

    currentAppVersion = ConfigItem(keys.VERSION_CURRENT_SECTION, "App", "")
    currentPowerVersion = ConfigItem(keys.VERSION_CURRENT_SECTION, "Power", "")
    currentUpperVersion = ConfigItem(keys.VERSION_CURRENT_SECTION, "Upper", "")
    latestAppVersion = ConfigItem(keys.VERSION_LATEST_SECTION, "App", "")
    latestPowerVersion = ConfigItem(keys.VERSION_LATEST_SECTION, "Power", "")
    latestUpperVersion = ConfigItem(keys.VERSION_LATEST_SECTION, "Upper", "")

    appYear = ConfigItem("Application", "Year", 2026)
    appAuthor = ConfigItem("Application", "Author", "UF4OVER")
    appHelpUrl = ConfigItem("Application", "HelpUrl", "https://update.hepi.ng/docs/help")
    appRepoUrl = ConfigItem("Application", "RepoUrl", keys.APP_REPOSITORY_URL)
    appExampleUrl = ConfigItem("Application", "ExampleUrl", "https://github.com/UF4OVER/UF4DigitalPower")
    appFeedbackUrl = ConfigItem("Application", "FeedbackUrl", "https://github.com/UF4OVER/UF4DigitalPower/issues")
    appReleaseUrl = ConfigItem("Application", "ReleaseUrl", keys.APP_REPOSITORY_URL + "/releases/latest")
    appZhSupportUrl = ConfigItem("Application", "ZhSupportUrl", "https://github.com/UF4OVER/UF4DigitalPower")
    appEnSupportUrl = ConfigItem("Application", "EnSupportUrl", "https://github.com/UF4OVER/UF4DigitalPower")

    fontFile = ConfigItem("Appearance", "FontFile", "__system__")
    fontFamily = ConfigItem("Appearance", "FontFamily", "")

    # DAPLink 下载工具路径（留空时自动探测）
    daplinkUf4TargetExe = ConfigItem("Daplink", "Uf4TargetExe", "")
    daplinkOpenocdExe = ConfigItem("Daplink", "OpenocdExe", "")

    # Compatibility aliases refer to the same items, never additional JSON fields.
    @property
    def appVersion(self):
        return self.currentAppVersion

    @property
    def localAppVersion(self):
        return self.currentAppVersion

    @property
    def localLowerVersion(self):
        return self.currentPowerVersion

    @property
    def localUpperVersion(self):
        return self.currentUpperVersion

    @property
    def latestLowerVersion(self):
        return self.latestPowerVersion

    def __init__(self):
        super().__init__()
        self._items: dict[str, ConfigItem] = {}
        for name in dir(type(self)):
            template = getattr(type(self), name)
            if not isinstance(template, ConfigItem):
                continue
            default = deepcopy(template.defaultValue)
            if isinstance(template, ColorConfigItem):
                item = ColorConfigItem(template.group, template.name, default, restart=template.restart)
            else:
                item = type(template)(template.group, template.name, default,
                                      validator=deepcopy(template.validator),
                                      serializer=deepcopy(template.serializer), restart=template.restart)
            item.defaultValue = deepcopy(template.defaultValue)
            item.setParent(self)
            setattr(self, name, item)
            self._items[name] = item

    def toDict(self, serialize: bool = True) -> dict:
        data: dict = {}
        for item in self._items.values():
            value = item.serialize() if serialize else item.value
            if item.name:
                data.setdefault(item.group, {})[item.name] = value
            else:
                data[item.group] = value
        return data

    def load(self, file: str | Path | None = None, config=None) -> None:
        if config is not None and config is not self:
            config.load(file)
            return
        if file is not None:
            self.file = Path(file)
        # Parse and validate first so a malformed file cannot partially reset settings.
        data = migrate_config(JsonConfigStore(self.file).read())
        values = {}
        for name, item in self._items.items():
            section = data.get(item.group)
            raw = section.get(item.name) if isinstance(section, dict) else section
            has_value = item.name in section if isinstance(section, dict) else not item.name and item.group in data
            value = deepcopy(item.defaultValue)
            if has_value:
                try:
                    value = item.validator.correct(item.serializer.deserialize(raw))
                except (TypeError, ValueError, KeyError, AttributeError) as exc:
                    _log.warning("Invalid setting %s; using its default: %s", item.key, exc)
            values[name] = value

        old_mode, old_theme, old_color = self.themeMode.value, self.theme, self.themeColor.value
        for name, value in values.items():
            self._items[name].value = value
        self.theme = self.themeMode.value
        if old_mode != self.themeMode.value or old_theme != self.theme:
            self.themeChanged.emit(self.themeMode.value)
            self.themeChangedFinished.emit()
        if old_color != self.themeColor.value:
            self.themeColorChanged.emit(self.themeColor.value)

    def save(self) -> None:
        store = JsonConfigStore(self.file)
        # Preserve extension/future fields, and refuse to overwrite malformed JSON.
        data = migrate_config(store.read())
        for group, values in self.toDict().items():
            if isinstance(values, dict) and isinstance(data.get(group), dict):
                data[group].update(values)
            else:
                data[group] = values
        store.write(data)


def bind_global_config(config: F4CPConfig) -> None:
    """Bridge Fluent's singleton to the application context, once per binding.

    QConfig stores its active config in _cfg and accesses common items directly on
    the singleton. Keep that library-specific integration here so injected contexts
    can load and save without rebinding the application's theme or storage.
    """
    if qconfig._cfg is config:
        return
    previous = qconfig._cfg
    signals = ("themeChanged", "themeChangedFinished", "themeColorChanged", "appRestartSig")
    if previous is not qconfig:
        for name in signals:
            try:
                getattr(previous, name).disconnect(getattr(qconfig, name))
            except (TypeError, RuntimeError):
                pass
    qconfig._cfg = config
    qconfig.toDict = config.toDict
    for name, item in config._items.items():
        setattr(qconfig, name, item)
    for name in ("appVersion", "localAppVersion", "localLowerVersion", "localUpperVersion", "latestLowerVersion"):
        setattr(qconfig, name, getattr(config, name))
    for name in signals:
        getattr(config, name).connect(getattr(qconfig, name))
