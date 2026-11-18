# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import FluentIconBase, NavigationItemPosition

from app.widgets.icon import UF4Icon
from app.widgets.pages import HomePage, SettingsPage, VersionPage, ProfilePage


@dataclass(frozen=True)
class NavigationEntry:
    attr_name: str
    interface_attr: str
    icon: FluentIconBase | QIcon | str
    text: str
    selected_icon: FluentIconBase | QIcon | str
    position: NavigationItemPosition = NavigationItemPosition.TOP


NAVIGATION_ENTRIES = (
    NavigationEntry("homeNavItem", "homeInterface", UF4Icon.GAUGE, "首页", UF4Icon.GAUGE_FILL),
    NavigationEntry("versionNavItem", "versionInterface", UF4Icon.CLOUD_ARROW_DOWN, "软件更新", UF4Icon.CLOUD_ARROW_DOWN_FILL),
    NavigationEntry("profileNavItem", "profileInterface", UF4Icon.BOARD, "个人", UF4Icon.BOARD, NavigationItemPosition.BOTTOM),
    NavigationEntry("settingNavItem", "settingInterface", UF4Icon.SERVER, "设置", UF4Icon.SERVER_FILL, NavigationItemPosition.BOTTOM),
)


class NavigationMixin:
    """Page construction and navigation registration."""

    def createPages(self) -> None:
        self.homeInterface = HomePage(self)
        self.versionInterface = VersionPage(self)
        self.settingInterface = SettingsPage(self)
        self.profileInterface = ProfilePage(self)

    def registerNavigation(self) -> None:
        for entry in NAVIGATION_ENTRIES:
            interface = getattr(self, entry.interface_attr)
            self._addNavigationEntry(entry, interface)

        self.navigationInterface.setCurrentItem(self.homeInterface.objectName())

    def _addNavigationEntry(self, entry: NavigationEntry, interface: QWidget) -> None:
        item = self.addSubInterface(
            interface,
            entry.icon,
            entry.text,
            entry.selected_icon,
            entry.position,
        )
        setattr(self, entry.attr_name, item)
