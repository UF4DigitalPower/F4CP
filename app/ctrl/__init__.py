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
    def bind(self) -> None:
        page = self.page
        if page is None:
            return
        page.refreshButton.clicked.connect(page.refreshCurrentConnectionTargets)
        page.connectButton.clicked.connect(page.toggleConnection)
        page.connectionTypeCombo.currentTextChanged.connect(page._onConnectionTypeChanged)
        page.modeCombo.currentIndexChanged.connect(page._applyMode)
        page.sendButton.clicked.connect(page.onSend)
        page.addTlvBtn.clicked.connect(page._addDefaultTlvRow)
        page.delTlvBtn.clicked.connect(page._deleteSelectedTlvRows)
        page.exportTlvBtn.clicked.connect(page._exportTlvJsonToTx)
        page.importTlvBtn.clicked.connect(page._importTlvJsonFromTx)
        page.clearButton.clicked.connect(page.logEdit.clear)


class PowerPageController(_NullPageController):
    def bind(self) -> None:
        page = self.page
        if page is None:
            return
        client = page._client

        page.refreshTargetButton.clicked.connect(page.refreshSerialPorts)
        page.connectButton.clicked.connect(page.toggleConnection)
        page.refreshButton.clicked.connect(page._readStatusOnce)
        page.autoPollSwitch.checkedChanged.connect(page._onAutoPollChanged)
        page.parameterEditor.outputSwitch.checkedChanged.connect(page._onOutputSwitchChanged)
        page.parameterEditor.clearFaultButton.clicked.connect(page._clearFault)
        page.parameterEditor.applyOutputButton.clicked.connect(page._applyOutputLimits)
        page.parameterEditor.applyProtectButton.clicked.connect(page._applyProtectionValues)
        page.clearLogButton.clicked.connect(page.logEdit.clear)

        page.attachSessionRequested.connect(client.attach_session)
        page.detachSessionRequested.connect(client.detach_session)
        page.readStatusRequested.connect(client.read_status)
        page.outputLimitsRequested.connect(client.write_output_limits)
        page.protectionValuesRequested.connect(client.write_protection_values)
        page.powerStateRequested.connect(client.write_power_state)
        page.clearFaultRequested.connect(client.clear_fault)
        page.startPollingRequested.connect(client.start_polling)
        page.stopPollingRequested.connect(client.stop_polling)

        client.connectionChanged.connect(page._onConnectionChanged)
        client.statusUpdated.connect(page._updateStatusView)
        client.errorOccurred.connect(page._onClientError)
        client.outputLimitsWritten.connect(page._onOutputLimitsWritten)
        client.protectionValuesWritten.connect(page._onProtectionValuesWritten)
        client.powerStateWritten.connect(page._onPowerStateWritten)
        client.faultClearWritten.connect(page._onFaultClearWritten)
        client.writeTransactionFinished.connect(page._onWriteTransactionFinished)
