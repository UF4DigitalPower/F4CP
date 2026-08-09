# -*- coding: utf-8 -*-


class _NullPageController:
    def __init__(self, page=None):
        self.page = page

    def bind(self) -> None:
        pass

    def scheduleStartupTasks(self) -> None:
        pass


class DaplinkPageController(_NullPageController):
    pass


class DevicePageController(_NullPageController):
    pass


class PowerPageController(_NullPageController):
    pass
