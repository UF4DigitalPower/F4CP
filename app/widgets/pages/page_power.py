# -*- coding: utf-8 -*-
# -------------------------------
#  @Project : F4CP
#  @Time    : 2026 - 01-08 12:30
#  @FileName: page_power.py
#  @FileType: 电源页面文件，负责电源监控、参数设置和日志展示
#  @Software: PyCharm 2024.1.6 (Professional Edition)
#  @System  : Windows 11 23H2
#  @Author  : UF4
#  @Contact :
#  @Python  : 3.10
# -------------------------------

import html
import math
import time
from dataclasses import dataclass

from PyQt5.QtCore import QMetaObject, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel, CardWidget, CaptionLabel, ComboBox, DoubleSpinBox,
    FluentIcon as FIF, PrimaryPushButton, PushButton,
    ScrollArea, SpinBox,
    StrongBodyLabel, SubtitleLabel, SwitchButton, TextEdit, TitleLabel,
    isDarkTheme, setFont,
)

from app.core.channel import ChannelConfig
from app.core.data_hub import DataHub
from app.core.utility import showMessage
from app.ctrl import PowerPageController
from app.manager import StyleSheet

from app.session.page_power.other_power import DEFAULT_STATUS_VALUES, build_status, listSerialPorts, pretty_faults
from app.session.page_power.session_power import F4CPPowerClient, PowerStatus, SerialConfig, SerialSession
from app.widgets.components import PageHeader
from app.widgets.components.chip import ChipTone, StatusChip as BaseStatusChip
from app.widgets.chart.chart_model import ChartModel
from app.widgets.chart.realtime_chart_widget import RealtimeChartWidget
from config import CTX, get_logger

logger = get_logger("PowerPage")


DEFAULT_OVP_SET_VALUE_CENTI_V = 4400
POWER_POLL_INTERVAL_MS = 500
POWER_SERIAL_BAUD_RATE = 921600
WRITE_POLL_RESTART_DELAY_MS = 600
WRITE_WATCHDOG_TIMEOUT_MS = 6500

POWER_CHART_CHANNELS = (
    ChannelConfig("vin", "输入电压", "V", precision=3, group="voltage", color=(47, 128, 237), line_width=2.0),
    ChannelConfig("vout", "输出电压", "V", precision=3, group="voltage", color=(39, 174, 96), line_width=2.0),
    ChannelConfig("iin", "输入电流", "A", precision=3, group="current", color=(242, 153, 74), line_width=2.0),
    ChannelConfig("iout", "输出电流", "A", precision=3, group="current", color=(235, 87, 87), line_width=2.0),
    ChannelConfig("pin", "输入功率", "W", precision=3, group="power", color=(86, 204, 242), line_width=2.0),
    ChannelConfig("pout", "输出功率", "W", precision=3, group="power", color=(155, 81, 224), line_width=2.0),
    ChannelConfig("efficiency", "效率", "%", precision=2, group="efficiency", color=(255, 193, 7), line_width=2.0),
    ChannelConfig("core_temp", "通道温度1", "°C", precision=2, group="thermal", color=(255, 112, 67), line_width=2.0),
    ChannelConfig("board_temp", "通道温度2", "°C", precision=2, group="thermal", color=(255, 152, 0), line_width=2.0),
)


@dataclass(frozen=True)
class _MetricValue:
    title: str
    value: str
    unit: str
    extra: str = ""


class MetricCard(CardWidget):
    def __init__(self, title: str, accent: str, parent=None):
        super().__init__(parent)
        self._accent = accent
        self.setObjectName("PowerMetricCard")
        self.titleLabel = CaptionLabel(title, self)
        self.valueLabel = TitleLabel("--", self)
        self.unitLabel = StrongBodyLabel("", self)
        self.extraLabel = CaptionLabel("等待数据", self)
        self.extraLabel.setWordWrap(True)
        self.valueLabel.setWordWrap(False)
        self.unitLabel.setWordWrap(False)
        self.unitLabel.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        self.unitLabel.setMinimumWidth(44)
        setFont(self.valueLabel, 24, QFont.DemiBold)
        setFont(self.unitLabel, 15, QFont.DemiBold)

        value_row = QHBoxLayout()
        value_row.setContentsMargins(0, 0, 0, 0)
        value_row.setSpacing(8)
        value_row.addWidget(self.valueLabel, 1)
        value_row.addWidget(self.unitLabel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(5)
        layout.addWidget(self.titleLabel)
        layout.addLayout(value_row)
        layout.addWidget(self.extraLabel)
        self.setMinimumHeight(108)
        self.setMaximumHeight(128)
        self.refreshTheme()

    def setMetric(self, metric: _MetricValue) -> None:
        self.titleLabel.setText(metric.title)
        self.valueLabel.setText(metric.value)
        self._setAccentText(self.unitLabel, metric.unit)
        self._setAccentText(self.extraLabel, metric.extra)

    def _setAccentText(self, label, text: str) -> None:
        if not text:
            label.setText("")
            return
        safe_text = html.escape(text).replace("\n", "<br/>")
        label.setText(f'<span style="color: {self._accent};">{safe_text}</span>')

    def refreshTheme(self) -> None:
        dark = isDarkTheme()
        text = "#F5F7FA" if dark else "#111827"
        self.titleLabel.setStyleSheet(f"color: {self._accent};")
        self.valueLabel.setStyleSheet(f"color: {text};")


class StatusChip(BaseStatusChip):
    """电源在线状态标签：在线=成功绿，离线=危险红，与 RO/RW 标签同一胶囊风格。"""

    def __init__(self, text: str = "离线", parent=None):
        super().__init__(text, ChipTone.DANGER, parent)
        self._online = False

    def setOnline(self, online: bool) -> None:
        self._online = bool(online)
        self.setText("在线" if self._online else "离线")
        super().setOnline(self._online)


class StatusValueWidget(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("PowerStatusValue")
        self.titleLabel = CaptionLabel(title, self)
        self.valueLabel = StrongBodyLabel("--", self)
        self.valueLabel.setWordWrap(True)
        self.valueLabel.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        setFont(self.titleLabel, 12)
        setFont(self.valueLabel, 14, QFont.DemiBold)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(2)
        layout.addWidget(self.titleLabel)
        layout.addWidget(self.valueLabel, 1)
        self.setMinimumHeight(62)
        self.setMinimumWidth(108)
        self.refreshTheme()

    def setValue(self, value: str) -> None:
        self.valueLabel.setText(value)

    def refreshTheme(self) -> None:
        dark = isDarkTheme()
        title = "#9AA4B2" if dark else "#64748B"
        value = "#F5F7FA" if dark else "#111827"
        border = "rgba(255, 255, 255, 0.10)" if dark else "rgba(15, 23, 42, 0.08)"
        background = "rgba(255, 255, 255, 0.045)" if dark else "rgba(248, 250, 252, 0.82)"
        self.titleLabel.setStyleSheet(f"color: {title};")
        self.valueLabel.setStyleSheet(f"color: {value};")
        self.setStyleSheet(f"""
            QWidget#PowerStatusValue {{
                background: {background};
                border: 1px solid {border};
                border-radius: 8px;
            }}
        """)


class ParameterEditor(CardWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("PowerParameterEditor")
        self.titleLabel = SubtitleLabel(title, self)
        self._selectorBlocks: list[tuple[QWidget, CaptionLabel]] = []
        self.outputVoltage = self._createDoubleSelector("V", 0.0, 80.0, 0.01)
        self.outputCurrent = self._createDoubleSelector("A", 0.0, 60.0, 0.01)
        self.ovp = self._createDoubleSelector("V", 0.0, 100.0, 0.01)
        self.ocp = self._createDoubleSelector("A", 0.0, 80.0, 0.01)
        self.otp = self._createDoubleSelector("°C", 0.0, 150.0, 0.01)
        self.fan = self._createFanSelector()
        for editor in (self.ovp, self.ocp, self.otp, self.fan):
            editor.setVisible(False)

        self._editors = (
            self.outputVoltage,
            self.outputCurrent,
            self.ovp,
            self.ocp,
            self.otp,
            self.fan,
        )
        self._updatingFromStatus = False
        self._dirtyEditors: set[QWidget] = set()
        for editor in self._editors:
            editor.valueChanged.connect(lambda _value, item=editor: self._markEditorDirty(item))
            try:
                editor.lineEdit().textEdited.connect(lambda _text, item=editor: self._markEditorDirty(item))
            except Exception:
                pass

        self.outputSwitch = SwitchButton(self)
        self.outputSwitch.setOnText("输出开启")
        self.outputSwitch.setOffText("输出关闭")
        self.applyOutputButton = PrimaryPushButton(FIF.ACCEPT, "应用输出", self)
        self.applyProtectButton = PushButton(FIF.SAVE, "应用保护", self)
        self.outputSwitch.setFixedHeight(32)
        self.applyOutputButton.setFixedHeight(32)
        self.applyProtectButton.setFixedHeight(32)
        self.applyOutputButton.setMinimumWidth(96)
        self.applyProtectButton.setMinimumWidth(96)
        self.applyProtectButton.setVisible(False)
        self._sectionLabels = [
            BodyLabel("输出设定", self),
        ]

        outputGrid = QGridLayout()
        outputGrid.setContentsMargins(0, 0, 0, 0)
        outputGrid.setHorizontalSpacing(10)
        outputGrid.setVerticalSpacing(8)
        outputGrid.addWidget(self._selectorBlock("输出电压", self.outputVoltage), 0, 0)
        outputGrid.addWidget(self._selectorBlock("输出电流", self.outputCurrent), 0, 1)
        outputGrid.setColumnStretch(0, 1)
        outputGrid.setColumnStretch(1, 1)

        control = QHBoxLayout()
        control.setContentsMargins(0, 6, 0, 0)
        control.setSpacing(10)
        control.addWidget(self.outputSwitch)
        control.addStretch(1)
        control.addWidget(self.applyOutputButton)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        layout.addWidget(self.titleLabel)
        layout.addWidget(self._sectionLabels[0])
        layout.addLayout(outputGrid)
        layout.addStretch(1)
        layout.addLayout(control)
        self.refreshTheme()

    def _createDoubleSelector(self, suffix: str, minimum: float, maximum: float, step: float) -> DoubleSpinBox:
        selector = DoubleSpinBox(self)
        selector.setRange(minimum, maximum)
        selector.setDecimals(3)
        selector.setSingleStep(step)
        selector.setSuffix(f" {suffix}")
        selector.setFixedHeight(32)
        selector.setMinimumWidth(104)
        selector.setAlignment(Qt.AlignmentFlag.AlignRight)
        selector.setAccelerated(True)
        return selector

    def _createFanSelector(self) -> SpinBox:
        selector = SpinBox(self)
        selector.setRange(0, 1000)
        selector.setSingleStep(10)
        selector.setSuffix(" /1000")
        selector.setFixedHeight(32)
        selector.setMinimumWidth(104)
        selector.setAlignment(Qt.AlignmentFlag.AlignRight)
        selector.setAccelerated(True)
        return selector

    def _selectorBlock(self, title: str, selector) -> QWidget:
        block = QWidget(self)
        block.setObjectName("PowerParameterBlock")
        label = CaptionLabel(title, block)
        setFont(label, 12)
        layout = QVBoxLayout(block)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)
        layout.addWidget(label)
        layout.addWidget(selector)
        block.setMinimumHeight(60)
        self._selectorBlocks.append((block, label))
        return block

    def refreshTheme(self) -> None:
        dark = isDarkTheme()
        title = "#F5F7FA" if dark else "#111827"
        caption = "#9AA4B2" if dark else "#64748B"
        border = "rgba(255, 255, 255, 0.10)" if dark else "rgba(15, 23, 42, 0.08)"
        background = "rgba(255, 255, 255, 0.045)" if dark else "rgba(248, 250, 252, 0.82)"
        self.titleLabel.setStyleSheet(f"color: {title};")
        for sectionLabel in self._sectionLabels:
            sectionLabel.setStyleSheet(f"color: {title}; font-weight: 700;")
        for block, label in self._selectorBlocks:
            label.setStyleSheet(f"color: {caption};")
            block.setStyleSheet(f"""
                QWidget#PowerParameterBlock {{
                    background: {background};
                    border: 1px solid {border};
                    border-radius: 8px;
                }}
            """)

    def setFromStatus(self, status: PowerStatus) -> None:
        values = {
            self.outputVoltage: status.set_voltage_limit_mv / 100.0,
            self.outputCurrent: status.set_current_limit_ma / 100.0,
            self.ovp: status.ovp_set_value_v,
            self.ocp: status.ocp_set_value_a,
            self.otp: status.otp_set_value_c,
            self.fan: status.fan_set_value,
        }
        self._updatingFromStatus = True
        try:
            for editor, value in values.items():
                if editor in self._dirtyEditors or self._selectorHasFocus(editor):
                    continue
                editor.setValue(value)
        finally:
            self._updatingFromStatus = False

    def _markEditorDirty(self, editor: QWidget) -> None:
        if not self._updatingFromStatus:
            self._dirtyEditors.add(editor)

    def clearOutputDirty(self) -> None:
        self._dirtyEditors.discard(self.outputVoltage)
        self._dirtyEditors.discard(self.outputCurrent)

    def clearProtectionDirty(self) -> None:
        self._dirtyEditors.discard(self.ovp)
        self._dirtyEditors.discard(self.ocp)
        self._dirtyEditors.discard(self.otp)
        self._dirtyEditors.discard(self.fan)

    def clearAllDirty(self) -> None:
        self._dirtyEditors.clear()

    @staticmethod
    def _selectorHasFocus(editor) -> bool:
        try:
            return editor.hasFocus() or editor.lineEdit().hasFocus()
        except Exception:
            return editor.hasFocus()

    def setWriteEnabled(self, enabled: bool) -> None:
        for editor in self._editors:
            editor.setEnabled(enabled)
        self.outputSwitch.setEnabled(enabled)
        self.applyOutputButton.setEnabled(enabled)
        self.applyProtectButton.setEnabled(enabled)


class TelemetryChartCard(CardWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TelemetryChartCard")
        self.dataHub = DataHub(default_max_points=6000)
        self.dataHub.register_channels(POWER_CHART_CHANNELS, max_points=6000)
        self.chartModel = ChartModel(self.dataHub)
        self.chartModel.set_time_window(30.0)
        self.chartModel.set_auto_y_range(True)
        self.titleLabel = SubtitleLabel("实时曲线", self)
        self.tipLabel = CaptionLabel("左键拖动平移时间轴，滚轮缩放时基，双击回到实时位置。", self)
        self.chart = RealtimeChartWidget(self.chartModel, self)
        self.chart.set_title("F4CP Power Telemetry")
        self.chart.setMinimumHeight(300)
        self.chart.setMaximumHeight(300)
        self.setMaximumHeight(382)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        layout.addWidget(self.titleLabel)
        layout.addWidget(self.tipLabel)
        layout.addWidget(self.chart, 1)
        self.refreshTheme()

    def refreshTheme(self) -> None:
        dark = isDarkTheme()
        self.titleLabel.setStyleSheet(f"color: {'#F5F7FA' if dark else '#111827'};")
        self.tipLabel.setStyleSheet(f"color: {'#9AA4B2' if dark else '#64748B'};")
        self.chart.refreshTheme()

    def pushStatus(self, status: PowerStatus) -> None:
        self.dataHub.push_many({
            "vin": status.vin_v, "vout": status.vout_v,
            "iin": status.iin_a, "iout": status.iout_a,
            "pin": status.pin_w, "pout": status.pout_w,
            "efficiency": status.efficiency,
            "core_temp": status.core_temp_c,
            "board_temp": status.board_temp_c,
        }, t=time.time())
        self.chart.mark_data_dirty()

    def pushMock(self) -> None:
        t = time.time()
        phase = t * 0.8
        vin = 16.8 + math.sin(phase) * 0.08
        vout = 12.0 + math.sin(phase * 1.2) * 0.18
        iin = 2.4 + math.sin(phase * 0.7) * 0.25
        iout = 3.0 + math.sin(phase * 0.9) * 0.35
        pin = vin * iin
        pout = vout * iout
        self.dataHub.push_many({
            "vin": vin, "vout": vout, "iin": iin, "iout": iout,
            "pin": pin, "pout": pout,
            "efficiency": 0.0 if pin <= 0 else pout / pin * 100.0,
            "core_temp": 42.0 + math.sin(phase * 0.25) * 2.0,
            "board_temp": 38.0 + math.sin(phase * 0.32) * 1.4,
        }, t=t)
        self.chart.mark_data_dirty()


class PowerPage(ScrollArea):
    attachSessionRequested = pyqtSignal(object)
    detachSessionRequested = pyqtSignal()
    readStatusRequested = pyqtSignal()
    outputLimitsRequested = pyqtSignal(int, int, bool)
    protectionValuesRequested = pyqtSignal(int, int, int, int)
    powerStateRequested = pyqtSignal(bool)
    startPollingRequested = pyqtSignal(int)
    stopPollingRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("PowerPage")

        self._shutdownDone = False
        self._manualSession = None
        self._lastStatus: PowerStatus | None = None
        self._stagedOutputEnabled: bool | None = None
        self._pendingOutputSettings: tuple[int, int] | None = None
        self._pendingProtectionSettings: tuple[int, int, int, int] | None = None
        self._writeInFlight = False
        self._writePollingRestartPending = False
        self._lastVerboseLogTs = 0.0
        self._appendLogBusy = False

        self._client = F4CPPowerClient()
        self._clientThread = QThread(self)
        self._client.moveToThread(self._clientThread)
        self._clientThread.finished.connect(self._client.deleteLater)
        self._clientThread.start()

        self._writePollRestartTimer = QTimer(self)
        self._writePollRestartTimer.setSingleShot(True)
        self._writePollRestartTimer.timeout.connect(self._restartAutoPollingAfterWrite)
        self._writeWatchdogTimer = QTimer(self)
        self._writeWatchdogTimer.setSingleShot(True)
        self._writeWatchdogTimer.timeout.connect(self._onWriteWatchdogTimeout)
        self._scrollIdleTimer = QTimer(self)
        self._scrollIdleTimer.setSingleShot(True)
        self._scrollIdleTimer.setInterval(180)
        self._scrollIdleTimer.timeout.connect(self._resumeChartAfterScroll)

        self.scrollWidget = QWidget(self)
        self.scrollWidget.setObjectName("powerScrollWidget")
        self.rootLayout = QVBoxLayout(self.scrollWidget)
        self.rootLayout.setContentsMargins(24, 24, 24, 24)
        self.rootLayout.setSpacing(12)

        self._initHeader()
        self._initMetricCards()
        self._initTelemetryChart()
        self._initStatusAndParameters()
        self._initLogCard()
        self._initEmptyStatusView()

        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setViewportMargins(0, 0, 0, 0)
        self.verticalScrollBar().valueChanged.connect(self._onScrollValueChanged)

        self._controller = PowerPageController(self)
        self._bindSignals()
        self._applyDisconnectedState()
        StyleSheet.POWER_PAGE.apply(self)
        CTX.cfg.themeChanged.connect(self._onThemeChanged)
        self.refreshSerialPorts()

    def _initHeader(self) -> None:
        self.header = PageHeader(
            "电源面板",
            "UF4 Digital Power 运行监控 / 输出设定 / 实时曲线",
            self.scrollWidget,
        )
        self.titleLabel = self.header.titleLabel
        self.subtitleLabel = self.header.subtitleLabel

        self.portCombo = ComboBox(self.header)
        self.portCombo.setMinimumWidth(140)
        self.refreshTargetButton = PushButton(FIF.SYNC, "刷新串口", self.header)
        self.connectButton = PrimaryPushButton(FIF.LINK, "连接", self.header)
        self.stateBadge = StatusChip("离线", self.header)
        self.autoPollSwitch = SwitchButton(self.header)
        self.autoPollSwitch.setOnText("自动轮询")
        self.autoPollSwitch.setOffText("自动轮询")
        self.autoPollSwitch.setChecked(True)
        self.refreshButton = PushButton(FIF.SYNC, "立即刷新", self.header)

        self.header.addAction(BodyLabel("串口", self.header))
        self.header.addActions((
            self.portCombo,
            self.refreshTargetButton,
            self.connectButton,
            self.stateBadge,
            self.autoPollSwitch,
            self.refreshButton,
        ))
        self.rootLayout.addWidget(self.header)

    def _initMetricCards(self) -> None:
        self.overviewRow = QHBoxLayout()
        self.overviewRow.setContentsMargins(0, 0, 0, 0)
        self.overviewRow.setSpacing(12)

        self.metricsHost = QWidget(self.scrollWidget)
        self.metricsGrid = QGridLayout()
        self.metricsGrid.setContentsMargins(0, 0, 0, 0)
        self.metricsGrid.setHorizontalSpacing(12)
        self.metricsGrid.setVerticalSpacing(8)
        self.metricCards = {
            "vin": MetricCard("输入电压", "#2F80ED", self.scrollWidget),
            "iin": MetricCard("输入电流", "#F2994A", self.scrollWidget),
            "pin": MetricCard("输入功率", "#56CCF2", self.scrollWidget),
            "vout": MetricCard("输出电压", "#27AE60", self.scrollWidget),
            "iout": MetricCard("输出电流", "#EB5757", self.scrollWidget),
            "pout": MetricCard("输出功率", "#9B51E0", self.scrollWidget),
        }
        for index, key in enumerate(("vin", "iin", "pin", "vout", "iout", "pout")):
            self.metricsGrid.addWidget(self.metricCards[key], index // 3, index % 3)
        for column in range(3):
            self.metricsGrid.setColumnStretch(column, 1)
        self.metricsHost.setLayout(self.metricsGrid)

        self.parameterEditor = ParameterEditor("输出设定", self.scrollWidget)
        self.parameterEditor.setMinimumWidth(300)
        self.parameterEditor.setMaximumWidth(340)
        self.parameterEditor.setMinimumHeight(224)
        self.parameterEditor.setMaximumHeight(224)

        self.overviewRow.addWidget(self.metricsHost, 1, Qt.AlignmentFlag.AlignTop)
        self.overviewRow.addWidget(self.parameterEditor, 0, Qt.AlignmentFlag.AlignTop)
        self.rootLayout.addLayout(self.overviewRow)

    def _initTelemetryChart(self) -> None:
        self.chartCard = TelemetryChartCard(self.scrollWidget)
        self.rootLayout.addWidget(self.chartCard)

    def _initStatusAndParameters(self) -> None:
        self.statusCard = CardWidget(self.scrollWidget)
        self.statusCard.setObjectName("PowerStatusCard")
        statusLayout = QVBoxLayout(self.statusCard)
        statusLayout.setContentsMargins(14, 12, 14, 14)
        statusLayout.setSpacing(8)
        self.statusTitle = SubtitleLabel("状态", self.statusCard)
        self.statusGrid = QGridLayout()
        self.statusGrid.setContentsMargins(0, 0, 0, 0)
        self.statusGrid.setHorizontalSpacing(8)
        self.statusGrid.setVerticalSpacing(8)
        self.statusFields = {
            "output": StatusValueWidget("输出", self.statusCard),
            "topology": StatusValueWidget("拓扑", self.statusCard),
            "mode": StatusValueWidget("控制模式", self.statusCard),
            "state": StatusValueWidget("状态机", self.statusCard),
            "fault": StatusValueWidget("故障", self.statusCard),
            "core_temp": StatusValueWidget("通道温度1", self.statusCard),
            "board_temp": StatusValueWidget("通道温度2", self.statusCard),
            "pwm": StatusValueWidget("PWM A/D", self.statusCard),
            "fan": StatusValueWidget("风扇", self.statusCard),
        }
        for index, key in enumerate((
            "output", "topology", "mode",
            "state", "fault", "core_temp",
            "board_temp", "pwm", "fan",
        )):
            self.statusGrid.addWidget(self.statusFields[key], index // 6, index % 6)
        for column in range(6):
            self.statusGrid.setColumnStretch(column, 1)
        statusLayout.addWidget(self.statusTitle)
        statusLayout.addLayout(self.statusGrid)
        self.rootLayout.addWidget(self.statusCard)

    def _initLogCard(self) -> None:
        self.logCard = CardWidget(self.scrollWidget)
        self.logCard.setObjectName("powerLogCard")
        layout = QVBoxLayout(self.logCard)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        top = QHBoxLayout()
        self.logCardTitle = SubtitleLabel("协议 / 状态日志", self.logCard)
        self.logLevelCombo = ComboBox(self.logCard)
        self.logLevelCombo.addItem("普通", userData="normal")
        self.logLevelCombo.addItem("详细", userData="verbose")
        self.clearLogButton = PushButton(FIF.BROOM, "清空", self.logCard)
        top.addWidget(self.logCardTitle)
        top.addStretch(1)
        top.addWidget(self.logLevelCombo)
        top.addWidget(self.clearLogButton)
        self.logEdit = TextEdit(self.logCard)
        self.logEdit.setMinimumHeight(170)
        self.logEdit.setReadOnly(True)
        self.logEdit.document().setMaximumBlockCount(400)
        layout.addLayout(top)
        layout.addWidget(self.logEdit)
        self.rootLayout.addWidget(self.logCard)

    def _onScrollValueChanged(self, _value: int) -> None:
        self.chartCard.chart.set_live_updates_suspended(True)
        self._scrollIdleTimer.start()

    def _resumeChartAfterScroll(self) -> None:
        self.chartCard.chart.set_live_updates_suspended(False)

    def _bindSignals(self) -> None:
        # 复杂信号注册下沉到 Controller，页面保留 UI 创建和状态渲染。
        self._controller.bind()

    def _onThemeChanged(self, *_):
        StyleSheet.POWER_PAGE.apply(self)
        self._refreshThemeWidgets()
        QTimer.singleShot(0, self._refreshThemeWidgets)

    def _refreshThemeWidgets(self) -> None:
        for card in self.metricCards.values():
            card.refreshTheme()
        for field in self.statusFields.values():
            field.refreshTheme()
        self.parameterEditor.refreshTheme()
        self.stateBadge.refreshTheme()
        self.chartCard.refreshTheme()

    def refreshSerialPorts(self) -> None:
        ports = [p.strip() for p in (listSerialPorts() or []) if p and p.strip()]
        current = self.portCombo.currentText().strip()
        self.portCombo.blockSignals(True)
        self.portCombo.clear()
        if ports:
            self.portCombo.addItems(ports)
            if current in ports:
                self.portCombo.setCurrentText(current)
        self.portCombo.blockSignals(False)
        logger.info(f"Serial ports: {ports}")

    def _initEmptyStatusView(self) -> None:
        self._renderStatusView(
            build_status(dict(DEFAULT_STATUS_VALUES)),
            update_chart=False,
            log_changes=False,
        )

    def toggleConnection(self) -> None:
        """连接按钮入口：根据当前状态在打开串口和断开会话之间切换。"""
        if self._client.is_connected:
            self._disconnectManualSession()
        else:
            self._connectSerialTarget()

    def _connectSerialTarget(self) -> None:
        """按页面选择创建串口会话，打开成功后交给电源协议客户端接管。"""
        port = self.portCombo.currentText().strip()
        if not port:
            message = "未选择串口。请先刷新并选择串口。"
            self._appendLog(f"错误: {message}")
            logger.warning(message)
            return
        session = SerialSession(SerialConfig(port=port, baudrate=POWER_SERIAL_BAUD_RATE))
        try:
            session.open()
        except Exception as exc:
            self.parameterEditor.setWriteEnabled(False)
            self._appendLog(f"错误: {exc}")
            logger.error(f"Failed to open serial port {port}: {exc}")
            return
        self._manualSession = session
        self.onDeviceConnected(session)

    def onDeviceConnected(self, session) -> None:
        """串口建立后同步 UI 状态，并按开关决定读一次还是持续轮询。"""
        port = getattr(getattr(session, 'cfg', None), 'port', '未知')
        self.attachSessionRequested.emit(session)
        self.stateBadge.setOnline(True)
        self.connectButton.setText("断开")
        self.parameterEditor.setWriteEnabled(True)
        self._appendLog(f"已连接: {port}")
        logger.info(f"Device session attached on {port}")
        showMessage(self, "设备已连接", "电源设备会话已连接。", level="success")
        if self.autoPollSwitch.isChecked():
            self.startPollingRequested.emit(POWER_POLL_INTERVAL_MS)
        else:
            self.readStatusRequested.emit()

    def _disconnectManualSession(self) -> None:
        """主动断开页面自己创建的串口会话，并让协议客户端清空状态。"""
        self.stopPollingRequested.emit()
        self.detachSessionRequested.emit()
        try:
            if self._manualSession:
                self._manualSession.close()
        except Exception as exc:
            logger.error(f"PowerPage manual session close failed: {exc}")
        self._manualSession = None
        self._applyDisconnectedState()
        self._appendLog("设备已断开")

    def _closeManualSessionSilently(self) -> None:
        session = self._manualSession
        self._manualSession = None
        if session is None:
            return
        try:
            session.set_event_receiver(None)
            session.close()
        except Exception as exc:
            logger.error(f"PowerPage serial cleanup failed: {exc}")

    def _onConnectionChanged(self, connected: bool) -> None:
        self.stateBadge.setOnline(connected)
        self.connectButton.setText("断开" if connected else "连接")
        self.parameterEditor.setWriteEnabled(connected)
        if not connected:
            self._closeManualSessionSilently()
            self._applyDisconnectedState()

    def _updateStatusView(self, status: PowerStatus) -> None:
        self._renderStatusView(status, update_chart=True, log_changes=True)

    def _renderStatusView(
        self,
        status: PowerStatus,
        *,
        update_chart: bool,
        log_changes: bool,
    ) -> None:
        """把一帧 PowerStatus 映射到指标卡、状态栏、参数编辑器和曲线图。"""
        previous = self._lastStatus
        if log_changes:
            self._lastStatus = status
        if update_chart:
            self.chartCard.pushStatus(status)
        self.metricCards["vin"].setMetric(_MetricValue("输入电压", f"{status.vin_v:.3f}", "V", f"输入功率 {status.pin_w:.2f} W"))
        self.metricCards["iin"].setMetric(_MetricValue("输入电流", f"{status.iin_a:.3f}", "A", f"模式 {status.mode_name}"))
        self.metricCards["pin"].setMetric(_MetricValue("输入功率", f"{status.pin_w:.3f}", "W", f"故障 0x{status.fault_state:04X}"))
        self.metricCards["vout"].setMetric(_MetricValue("输出电压", f"{status.vout_v:.3f}", "V", f"设定 {status.set_voltage_limit_mv / 100.0:.3f} V"))
        self.metricCards["iout"].setMetric(_MetricValue("输出电流", f"{status.iout_a:.3f}", "A", f"设定 {status.set_current_limit_ma / 100.0:.3f} A"))
        self.metricCards["pout"].setMetric(_MetricValue("输出功率", f"{status.pout_w:.3f}", "W", f"效率 {status.efficiency:.2f} %"))
        self._syncPendingParameterWrites(status)
        self.parameterEditor.setFromStatus(status)
        switch_value = status.power_enabled
        faulted = status.fault_state != 0
        if faulted:
            self._stagedOutputEnabled = None
        elif self._stagedOutputEnabled is not None:
            if self._stagedOutputEnabled == status.power_enabled:
                self._stagedOutputEnabled = None
            else:
                switch_value = self._stagedOutputEnabled
        self.parameterEditor.outputSwitch.blockSignals(True)
        self.parameterEditor.outputSwitch.setChecked(switch_value)
        self.parameterEditor.outputSwitch.blockSignals(False)
        faults = pretty_faults(status.fault_state)
        if not faults or faults == "None":
            faults = "无"
        self.statusFields["output"].setValue("开启" if status.power_enabled else "关闭")
        self.statusFields["topology"].setValue(status.topology_name)
        self.statusFields["mode"].setValue(status.mode_name)
        self.statusFields["state"].setValue(status.state_flag_name)
        self.statusFields["fault"].setValue(faults)
        self.statusFields["core_temp"].setValue(f"{status.core_temp_c:.2f} °C")
        self.statusFields["board_temp"].setValue(f"{status.board_temp_c:.2f} °C")
        self.statusFields["pwm"].setValue(f"{status.pwm_a_compare} / {status.pwm_d_compare}")
        self.statusFields["fan"].setValue(f"{status.fan_speed} / 设定 {status.fan_set_value}")
        if log_changes and (
            previous is None
            or previous.power_state != status.power_state
            or previous.state_machine_flag_bits != status.state_machine_flag_bits
            or previous.fault_state != status.fault_state
        ):
            self._appendLog(f"状态 输出={'开启' if status.power_enabled else '关闭'} 状态机={status.state_flag_name} 拓扑={status.topology_name} 故障={faults} VOUT={status.vout_v:.3f}V IOUT={status.iout_a:.3f}A")
            if faulted and (previous is None or previous.fault_state != status.fault_state):
                self._appendLog(f"保护触发：已停止输出，故障={faults} (0x{status.fault_state:04X})")
        if log_changes and self.logLevelCombo.currentData() == "verbose" and time.monotonic() - self._lastVerboseLogTs >= 2.0:
            self._lastVerboseLogTs = time.monotonic()
            self._appendLog(self._client.pretty_print_status(status))

    def _readStatusOnce(self) -> None:
        if not self._client.is_connected:
            self._appendLog("错误: 串口会话未连接")
            return
        self.readStatusRequested.emit()

    def _onAutoPollChanged(self, checked: bool) -> None:
        """自动轮询开关变化时，直接通知协议客户端启动或停止刷新。"""
        if checked:
            self.startPollingRequested.emit(POWER_POLL_INTERVAL_MS)
        else:
            self.stopPollingRequested.emit()
            self._appendLog("主机轮询已关闭")

    def _onOutputSwitchChanged(self, checked: bool) -> None:
        """输出开关先暂存用户意图，再交给协议层写入，避免界面被旧状态立刻覆盖。"""
        self._stagedOutputEnabled = checked
        if not self._client.is_connected:
            return
        if self._isWriteBlocked():
            return
        if self._client.is_busy:
            self._appendLog("协议请求进行中，请稍后再写入")
            return
        self._beginWriteOperation()
        self._writePollingRestartPending = True
        self._appendLog(f"输出开关正在设置为{'开启' if checked else '关闭'}")
        self.powerStateRequested.emit(checked)

    def _applyOutputLimits(self) -> None:
        """提交输出限制值；界面用 V/A，协议层用0.01 V/0.01 A。"""
        if not self._client.is_connected:
            self._appendLog("错误: 串口会话未连接")
            return
        if self._isWriteBlocked():
            return
        if self._client.is_busy:
            self._appendLog("协议请求进行中，请稍后再写入")
            return
        voltage_mv = int(round(self.parameterEditor.outputVoltage.value() * 100))
        current_ma = int(round(self.parameterEditor.outputCurrent.value() * 100))
        enabled = self._stagedOutputEnabled if self._stagedOutputEnabled is not None else self.parameterEditor.outputSwitch.isChecked()
        self._pendingOutputSettings = (voltage_mv, current_ma)
        self._beginWriteOperation()
        self._writePollingRestartPending = True
        self.outputLimitsRequested.emit(voltage_mv, current_ma, enabled)

    def _applyProtectionValues(self) -> None:
        """提交保护参数；电压、电流、温度统一按0.01单位传输。"""
        if not self._client.is_connected:
            self._appendLog("错误: 串口会话未连接")
            return
        if self._isWriteBlocked():
            return
        if self._client.is_busy:
            self._appendLog("协议请求进行中，请稍后再写入")
            return
        ovp_mv = int(round(self.parameterEditor.ovp.value() * 100))
        ocp_ma = int(round(self.parameterEditor.ocp.value() * 100))
        otp_mc = int(round(self.parameterEditor.otp.value() * 100))
        fan_value = int(self.parameterEditor.fan.value())
        self._pendingProtectionSettings = (ovp_mv, ocp_ma, otp_mc, fan_value)
        self._beginWriteOperation()
        self._writePollingRestartPending = True
        self.protectionValuesRequested.emit(ovp_mv, ocp_ma, otp_mc, fan_value)

    def _syncPendingParameterWrites(self, status: PowerStatus) -> None:
        """读回值确认后再允许状态流刷新刚编辑过的设定框。"""
        if self._pendingOutputSettings is not None:
            voltage_mv, current_ma = self._pendingOutputSettings
            editor_voltage_mv = int(round(self.parameterEditor.outputVoltage.value() * 100))
            editor_current_ma = int(round(self.parameterEditor.outputCurrent.value() * 100))
            if (
                status.set_voltage_limit_mv == voltage_mv
                and status.set_current_limit_ma == current_ma
                and editor_voltage_mv == voltage_mv
                and editor_current_ma == current_ma
            ):
                self.parameterEditor.clearOutputDirty()
                self._pendingOutputSettings = None

        if self._pendingProtectionSettings is not None:
            ovp_mv, ocp_ma, otp_mc, fan_value = self._pendingProtectionSettings
            editor_ovp_mv = int(round(self.parameterEditor.ovp.value() * 100))
            editor_ocp_ma = int(round(self.parameterEditor.ocp.value() * 100))
            editor_otp_mc = int(round(self.parameterEditor.otp.value() * 100))
            editor_fan_value = int(self.parameterEditor.fan.value())
            if (
                status.ovp_set_value_mv == ovp_mv
                and status.ocp_set_value_ma == ocp_ma
                and status.otp_set_value_mc == otp_mc
                and status.fan_set_value == fan_value
                and editor_ovp_mv == ovp_mv
                and editor_ocp_ma == ocp_ma
                and editor_otp_mc == otp_mc
                and editor_fan_value == fan_value
            ):
                self.parameterEditor.clearProtectionDirty()
                self._pendingProtectionSettings = None

    def _setWriteControlsEnabled(self, enabled: bool) -> None:
        self._writeInFlight = not enabled
        self.parameterEditor.setWriteEnabled(enabled)
        if enabled:
            self._writeWatchdogTimer.stop()

    def _beginWriteOperation(self) -> None:
        self._setWriteControlsEnabled(False)
        self._writeWatchdogTimer.start(WRITE_WATCHDOG_TIMEOUT_MS)

    def _isWriteBlocked(self) -> bool:
        if not self._writeInFlight:
            return False
        if not self._client.is_busy:
            self._appendLog("上次写入已结束，已恢复写入状态")
            self._setWriteControlsEnabled(True)
            return False
        if not self._writeWatchdogTimer.isActive():
            self._writeWatchdogTimer.start(WRITE_WATCHDOG_TIMEOUT_MS)
        self._appendLog("写入进行中，请等待当前操作完成")
        return True

    def _onWriteWatchdogTimeout(self) -> None:
        if not self._writeInFlight:
            return
        self._writeInFlight = False
        self.parameterEditor.setWriteEnabled(self._client.is_connected)
        self._appendLog("写入等待超时，已恢复按钮；若设备仍忙，请稍后再写")
        logger.error("Power write watchdog released UI controls")
        if self._writePollingRestartPending:
            self._scheduleAutoPollingRestartAfterWrite()

    def _onOutputLimitsWritten(self) -> None:
        self._setWriteControlsEnabled(True)
        showMessage(self, "输出参数已更新", "电压、电流和输出状态已写入。", level="success")
        self._scheduleAutoPollingRestartAfterWrite()

    def _onProtectionValuesWritten(self) -> None:
        self._setWriteControlsEnabled(True)
        showMessage(self, "保护参数已更新", "OVP/OCP/OTP/风扇参数已写入。", level="success")
        self._scheduleAutoPollingRestartAfterWrite()

    def _onPowerStateWritten(self, enabled: bool) -> None:
        self._setWriteControlsEnabled(True)
        if self._stagedOutputEnabled == enabled:
            self._stagedOutputEnabled = None
        self._appendLog(f"输出已设置为{'开启' if enabled else '关闭'}")
        self._scheduleAutoPollingRestartAfterWrite()

    def _onWriteTransactionFinished(self) -> None:
        if self._writeInFlight:
            self._setWriteControlsEnabled(True)

    def _onClientError(self, message: str) -> None:
        """协议层错误统一落到这里，恢复按钮状态并给用户一个明确提示。"""
        self._appendLog(f"错误: {message}")
        logger.error(f"Power client error: {message}")
        self._setWriteControlsEnabled(True)
        showMessage(self, "通信错误", message, level="error")
        if self._writePollingRestartPending:
            self._scheduleAutoPollingRestartAfterWrite()

    def _disconnectAfterWriteFailures(self) -> None:
        if not self._client.is_connected and self._manualSession is None:
            return
        self._appendLog("连续写入失败 3 次，已断开串口")
        showMessage(self, "串口已断开", "连续写入失败 3 次，已关闭当前串口连接。", level="error")
        self._disconnectManualSession()

    def _disconnectAfterCommunicationFailures(self, message: str) -> None:
        if not self._client.is_connected and self._manualSession is None:
            return
        self._appendLog(f"连续通信失败 3 次，已断开串口。最后错误: {message}")
        showMessage(self, "串口已断开", "连续 3 次无回复或错误，已关闭当前串口连接。", level="error")
        self._disconnectManualSession()

    def _scheduleAutoPollingRestartAfterWrite(self) -> None:
        """写操作结束后延迟恢复轮询，给设备一点时间完成内部状态更新。"""
        self._writePollingRestartPending = False
        self._writePollRestartTimer.stop()
        self._writePollRestartTimer.start(WRITE_POLL_RESTART_DELAY_MS)

    def _restartAutoPollingAfterWrite(self) -> None:
        if self._shutdownDone or not self.autoPollSwitch.isChecked() or not self._client.is_connected:
            return
        self.startPollingRequested.emit(POWER_POLL_INTERVAL_MS)
        self._appendLog("写入后已请求重启主机轮询")

    def _applyDisconnectedState(self) -> None:
        """回到离线 UI 状态，清掉暂存开关和正在写入的标记。"""
        self._stagedOutputEnabled = None
        self._pendingOutputSettings = None
        self._pendingProtectionSettings = None
        self._writePollingRestartPending = False
        self._setWriteControlsEnabled(False)
        self._writePollRestartTimer.stop()
        self.parameterEditor.clearAllDirty()
        self.stateBadge.setOnline(False)
        self.connectButton.setText("连接")
        self.parameterEditor.outputSwitch.blockSignals(True)
        self.parameterEditor.outputSwitch.setChecked(False)
        self.parameterEditor.outputSwitch.blockSignals(False)
        if self.parameterEditor.ovp.value() <= 0:
            self.parameterEditor.ovp.setValue(DEFAULT_OVP_SET_VALUE_CENTI_V / 100.0)


    def _appendLog(self, text: str) -> None:
        if self._appendLogBusy:
            return
        self._appendLogBusy = True
        try:
            # 只有非频繁的原始数据包才记录到文件日志，避免日志爆炸。
            if not (text.startswith("RX ") or text.startswith("TX ")):
                logger.info(text)

            ts = time.strftime("%H:%M:%S")
            if getattr(self, "logEdit", None) is not None:
                self.logEdit.append(f"[{ts}] {text}")
        finally:
            self._appendLogBusy = False

    def suspendForDaplink(self) -> None:
        self._appendLog("DAPLink 操作开始，已暂停主机轮询。")
        self.stopPollingRequested.emit()

    def resumeAfterDaplink(self) -> None:
        if self._shutdownDone:
            return
        if self.autoPollSwitch.isChecked() and self._client.is_connected:
            self.startPollingRequested.emit(POWER_POLL_INTERVAL_MS)
            self._appendLog("DAPLink 操作结束，已恢复主机轮询。")

    def closeEvent(self, event) -> None:
        self.shutdown()
        super().closeEvent(event)

    def shutdown(self) -> None:
        if self._shutdownDone:
            return
        self._shutdownDone = True
        self._writePollRestartTimer.stop()
        try:
            if self._manualSession:
                self._manualSession.close()
        except Exception as exc:
            logger.error(f"PowerPage manual session shutdown failed: {exc}")
        self._manualSession = None
        try:
            if self._clientThread.isRunning():
                QMetaObject.invokeMethod(self._client, "shutdown", Qt.ConnectionType.BlockingQueuedConnection)
        except Exception as exc:
            logger.error(f"PowerPage client shutdown failed: {exc}")
        if self._clientThread.isRunning():
            self._clientThread.quit()
            if not self._clientThread.wait(3000):
                logger.error("PowerPage client thread did not exit within 3000 ms")
