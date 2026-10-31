# -*- coding: utf-8 -*-
# -------------------------------
#  @Project : F4CP
#  @Time    : 2026 - 01-08 12:30
#  @FileName: constants.py
#  @FileType: 配置常量文件，集中管理配置分组、键名和默认仓库地址
#  @Software: PyCharm 2024.1.6 (Professional Edition)
#  @System  : Windows 11 23H2
#  @Author  : UF4
#  @Contact :
#  @Python  : 3.11
# -------------------------------

"""Shared JSON keys and application repository defaults."""

APP_REPOSITORY_URL = "https://github.com/UF4DigitalPower/F4CP"
LEGACY_APP_REPOSITORY_URL = "https://github.com/UF4OVER/UF4DigitalPower"

VERSION_CURRENT_SECTION = "VersionCurrent"
VERSION_LATEST_SECTION = "VersionLatest"
VERSION_LOCAL_SECTION = VERSION_CURRENT_SECTION
VERSION_REMOTE_SECTION = VERSION_LATEST_SECTION
UPDATE_SECTION = "Update"
FIRMWARE_REMOTE_SECTION = "FirmwareRemote"

LOCAL_APP_VERSION_OPTION = "App"
LOCAL_UPPER_VERSION_OPTION = "Upper"
LOCAL_LOWER_VERSION_OPTION = "Power"
LATEST_APP_VERSION_OPTION = "App"
LATEST_UPPER_VERSION_OPTION = "Upper"
LATEST_LOWER_VERSION_OPTION = "Power"
UPDATE_URL_OPTION = "UpdateUrl"
FIRMWARE_GITHUB_OWNER_OPTION = "GithubOwner"
FIRMWARE_GITHUB_REPO_OPTION = "GithubRepo"
FIRMWARE_BASE_URL_OPTION = "BaseUrl"

# Attribute names rather than snapshots keep module-level metadata current on reload.
APPLICATION_EXPORTS = {
    "YEAR": "appYear", "AUTHOR": "appAuthor", "VERSION": "appVersion",
    "HELP_URL": "appHelpUrl", "REPO_URL": "appRepoUrl", "EXAMPLE_URL": "appExampleUrl",
    "FEEDBACK_URL": "appFeedbackUrl", "RELEASE_URL": "appReleaseUrl",
    "ZH_SUPPORT_URL": "appZhSupportUrl", "EN_SUPPORT_URL": "appEnSupportUrl",
}

__all__ = [
    "APP_REPOSITORY_URL", "LEGACY_APP_REPOSITORY_URL",
    "VERSION_LOCAL_SECTION", "VERSION_REMOTE_SECTION", "UPDATE_SECTION", "FIRMWARE_REMOTE_SECTION",
    "VERSION_CURRENT_SECTION", "VERSION_LATEST_SECTION",
    "LOCAL_APP_VERSION_OPTION", "LOCAL_UPPER_VERSION_OPTION", "LOCAL_LOWER_VERSION_OPTION",
    "LATEST_APP_VERSION_OPTION", "LATEST_UPPER_VERSION_OPTION", "LATEST_LOWER_VERSION_OPTION",
    "UPDATE_URL_OPTION", "FIRMWARE_GITHUB_OWNER_OPTION", "FIRMWARE_GITHUB_REPO_OPTION", "FIRMWARE_BASE_URL_OPTION",
]
