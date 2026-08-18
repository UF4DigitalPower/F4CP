# -*- coding: utf-8 -*-
"""页面控制器：把 UI 信号统一绑定到页面动作方法。

DaplinkPageController 负责 DAPLink 下载页面的全部交互接线：
- 扫描/连接/下载/重载目标等按钮
- 下拉框、固件来源切换
- 启动任务：预加载目标 + 扫描调试器
"""

from __future__ import annotations


class _NullPageController:
    def __init__(self, page=None):
        self.page = page

    def bind(self) -> None:
        pass

    def scheduleStartupTasks(self) -> None:
        pass


class DaplinkPageController(_NullPageController):
    """DAPLink 下载页面控制器。"""

    def bind(self) -> None:
        page = self.page
        if page is None:
            return

        # 连接卡片
        page.scanProbeBtn.clicked.connect(page.scanProbe)
        page.connectBtn.clicked.connect(page.readInfo)
        page.reloadPackBtn.clicked.connect(page.reloadPackTargets)
        page.targetCombo.currentIndexChanged.connect(page._onTargetChanged)

        # 固件来源
        page.firmwareSourceCombo.currentIndexChanged.connect(page._onFirmwareSourceChanged)
        page.internalFirmwareCombo.currentIndexChanged.connect(page._onInternalFirmwareChanged)
        page.refreshFirmwareButton.clicked.connect(page._reloadInternalFirmwareOptions)
        page.browseButton.clicked.connect(page.browseFile)

        # 下载
        page.downloadButton.clicked.connect(page.startDownload)
        page.scanEsp32PortButton.clicked.connect(page.scanEsp32Ports)
        page.browseEsp32FileButton.clicked.connect(page.browseEsp32File)
        page.esp32FlashButton.clicked.connect(page.startEsp32Flash)
        page.esp32ResetButton.clicked.connect(page.resetEsp32)

        # 日志
        page.clearLogButton.clicked.connect(page.clearLog)
        page.saveLogButton.clicked.connect(page.saveLog)

    def scheduleStartupTasks(self) -> None:
        page = self.page
        if page is None:
            return
        # 启动时预加载目标表并扫描调试器（静默模式）
        page.preloadPackTargets()
        page.scanProbe()
        page.scanEsp32Ports()


class DevicePageController(_NullPageController):
    pass


class PowerPageController(_NullPageController):
    pass
