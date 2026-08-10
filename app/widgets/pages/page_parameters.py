# -*- coding: utf-8 -*-
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QAbstractSpinBox, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    FluentIcon as FIF,
    InfoBar,
    PrimaryPushButton,
    PushButton,
    ScrollArea,
    SpinBox,
    StrongBodyLabel,
    TitleLabel,
    setFont,
)
from app.core.parameter_manager import PARAMETER_SPECS, ParameterManager, ParameterSpec
from app.widgets.components import ChipTone, PageHeader, StatusChip


class AccessChip(StatusChip):
    """RO/RW 权限标签：RO=中性灰，RW=成功绿，与连接状态标签同一胶囊风格。"""

    def __init__(self, access: str, parent=None):
        tone = ChipTone.SUCCESS if access == "RW" else ChipTone.NEUTRAL
        super().__init__(access, tone, parent)


class ParameterRow(QWidget):
    def __init__(self, spec: ParameterSpec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.nameLabel = StrongBodyLabel(spec.name, self)
        self.metaLabel = CaptionLabel(f"{spec.note} / ID {spec.uf4_id} / {spec.minimum}..{spec.maximum}", self)
        self.accessLabel = AccessChip(spec.access, self)
        self.valueBox = SpinBox(self)
        self.unitLabel = BodyLabel(spec.unit, self)

        self.valueBox.setRange(spec.minimum, spec.maximum)
        self.valueBox.setValue(spec.default)
        self.valueBox.setMinimumWidth(150)
        if spec.access == "RO":
            self.valueBox.setReadOnly(True)
            self.valueBox.setButtonSymbols(QAbstractSpinBox.NoButtons)
            self.valueBox.setFocusPolicy(Qt.NoFocus)
        self.unitLabel.setMinimumWidth(84)
        self.unitLabel.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        textLayout = QVBoxLayout()
        textLayout.setContentsMargins(0, 0, 0, 0)
        textLayout.setSpacing(2)
        textLayout.addWidget(self.nameLabel)
        textLayout.addWidget(self.metaLabel)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(12)
        layout.addLayout(textLayout, 1)
        layout.addWidget(self.accessLabel)
        layout.addWidget(self.valueBox)
        layout.addWidget(self.unitLabel)

    def resetValue(self) -> None:
        if self.spec.access == "RW":
            self.valueBox.setValue(self.spec.default)

    def setValue(self, value: int) -> None:
        self.valueBox.setValue(int(value))

    def value(self) -> int:
        return int(self.valueBox.value())


class ParameterGroupCard(CardWidget):
    def __init__(self, title: str, specs: list[ParameterSpec], parent=None):
        super().__init__(parent)
        self.rows: list[ParameterRow] = []
        writable_count = sum(1 for spec in specs if spec.access == "RW")
        readonly_count = len(specs) - writable_count
        count_text = f"{len(specs)} 项"
        if writable_count and readonly_count:
            count_text += f" / RW {writable_count} / RO {readonly_count}"
        elif writable_count:
            count_text += f" / RW {writable_count}"
        elif readonly_count:
            count_text += f" / RO {readonly_count}"
        self.titleLabel = BodyLabel(f"{title}  {count_text}", self)
        setFont(self.titleLabel, 16, QFont.DemiBold)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(6)
        layout.addWidget(self.titleLabel)

        for spec in specs:
            row = ParameterRow(spec, self)
            self.rows.append(row)
            layout.addWidget(row)

    def resetValues(self) -> None:
        for row in self.rows:
            row.resetValue()

    def setValues(self, values: dict[str, int]) -> None:
        for row in self.rows:
            if row.spec.note in values:
                row.setValue(values[row.spec.note])

    def values(self) -> dict[str, int]:
        return {row.spec.note: row.value() for row in self.rows if row.spec.access == "RW"}


class ParametersPage(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scrollWidget = QWidget()
        self.mainLayout = QVBoxLayout(self.scrollWidget)
        self.groupCards: list[ParameterGroupCard] = []
        self.parameterManager = ParameterManager()

        self.readButton = PushButton(FIF.SYNC, "读取", self.scrollWidget)
        self.resetButton = PushButton(FIF.BROOM, "恢复默认", self.scrollWidget)
        self.saveButton = PrimaryPushButton(FIF.SAVE, "保存参数", self.scrollWidget)
        total_count = len(PARAMETER_SPECS)
        writable_count = sum(1 for spec in PARAMETER_SPECS if spec.access == "RW")
        readonly_count = total_count - writable_count
        self.header = PageHeader(
            "参数设置",
            f"参数来源：STM32G474RBT6 / uf4com.h + parameter_manager.c，"
            f"共 {total_count} 项，RW {writable_count} 项，RO {readonly_count} 项",
            self.scrollWidget,
        )
        self.titleLabel = self.header.titleLabel
        self.sourceLabel = self.header.subtitleLabel

        self.__initWidget()

    def __initWidget(self) -> None:
        self.setObjectName("ParametersPage")
        self.scrollWidget.setObjectName("parametersScrollWidget")
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setViewportMargins(0, 0, 0, 18)

        self.__initLayout()
        self.__connectSignals()
        self.__applyLocalStyle()
        self.__syncRowsFromManager()

    def __initLayout(self) -> None:
        self.header.addActions((self.readButton, self.resetButton, self.saveButton))

        self.mainLayout.setContentsMargins(36, 24, 36, 0)
        self.mainLayout.setSpacing(18)
        self.mainLayout.addWidget(self.header)

        grouped: dict[str, list[ParameterSpec]] = {}
        for spec in PARAMETER_SPECS:
            grouped.setdefault(spec.group, []).append(spec)

        columnsHost = QWidget(self.scrollWidget)
        columnsLayout = QHBoxLayout(columnsHost)
        columnsLayout.setContentsMargins(0, 0, 0, 0)
        columnsLayout.setSpacing(18)

        leftColumn = QWidget(columnsHost)
        rightColumn = QWidget(columnsHost)
        leftLayout = QVBoxLayout(leftColumn)
        rightLayout = QVBoxLayout(rightColumn)
        for columnLayout in (leftLayout, rightLayout):
            columnLayout.setContentsMargins(0, 0, 0, 0)
            columnLayout.setSpacing(18)

        columnLoads = [0, 0]
        columnLayouts = [leftLayout, rightLayout]
        for title, specs in grouped.items():
            columnIndex = 0 if columnLoads[0] <= columnLoads[1] else 1
            card = ParameterGroupCard(title, specs, columnsHost)
            self.groupCards.append(card)
            columnLayouts[columnIndex].addWidget(card)
            columnLoads[columnIndex] += len(specs)

        leftLayout.addStretch(1)
        rightLayout.addStretch(1)
        columnsLayout.addWidget(leftColumn, 1)
        columnsLayout.addWidget(rightColumn, 1)

        self.mainLayout.addWidget(columnsHost)
        self.mainLayout.addStretch(1)

    def __connectSignals(self) -> None:
        self.readButton.clicked.connect(self.__loadLocalParameters)
        self.saveButton.clicked.connect(self.__saveLocalParameters)
        self.resetButton.clicked.connect(self.__resetDefaults)

    def __resetDefaults(self) -> None:
        self.parameterManager.reset_defaults()
        for card in self.groupCards:
            card.resetValues()
        InfoBar.success("已恢复默认", "当前仅恢复界面里的 RW 默认参数值。", duration=1800, parent=self)

    def __loadLocalParameters(self) -> None:
        loaded = self.parameterManager.load()
        self.__syncRowsFromManager()
        if loaded:
            InfoBar.success("已读取", "已加载本地持久化参数快照。", duration=1800, parent=self)
        else:
            InfoBar.info("没有快照", "未找到有效本地参数快照，保持当前默认值。", duration=2200, parent=self)

    def __saveLocalParameters(self) -> None:
        try:
            self.parameterManager.write_many(self.__rowValues())
            self.parameterManager.save()
        except ValueError as exc:
            InfoBar.error("保存失败", str(exc), duration=2600, parent=self)
            return
        InfoBar.success("已保存", "持久化 RW 参数已保存到本地快照。", duration=1800, parent=self)

    def __syncRowsFromManager(self) -> None:
        values = {spec.note: self.parameterManager.read(spec.note) for spec in PARAMETER_SPECS}
        for card in self.groupCards:
            card.setValues(values)

    def __rowValues(self) -> dict[str, int]:
        values: dict[str, int] = {}
        for card in self.groupCards:
            values.update(card.values())
        return values

    def __applyLocalStyle(self) -> None:
        self.setStyleSheet("""
            QScrollArea#ParametersPage,
            QWidget#parametersScrollWidget {
                background: transparent;
                border: none;
            }
        """)

