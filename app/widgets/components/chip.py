# -*- coding: utf-8 -*-
# -------------------------------
#  @Project : F4CP
#  @Time    : 2026-08-10
#  @FileName: chip.py
#  @FileType: 统一胶囊标签组件（RO/RW、连接状态等短文本），按语义色调着色
#  @Software: PyCharm
#  @Author  : UF4
#  @Contact :
#  @Python  : 3.11
# -------------------------------

from __future__ import annotations

from enum import Enum

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QLabel
from qfluentwidgets import isDarkTheme, setFont


class ChipTone(Enum):
    """胶囊标签的语义色调：中性(RO/信息)、成功(RW/在线)、危险(未连接/离线)。"""
    NEUTRAL = "neutral"
    SUCCESS = "success"
    DANGER = "danger"


# (前景色, 背景色, 边框色)，按深色/浅色主题各一组
_CHIP_PALETTE = {
    ChipTone.NEUTRAL: {
        "dark": ("#CBD5E1", "rgba(148, 163, 184, 0.18)", "rgba(148, 163, 184, 0.30)"),
        "light": ("#475569", "rgba(148, 163, 184, 0.18)", "rgba(148, 163, 184, 0.30)"),
    },
    ChipTone.SUCCESS: {
        "dark": ("#22C55E", "rgba(34, 197, 94, 0.22)", "rgba(34, 197, 94, 0.36)"),
        "light": ("#166534", "rgba(34, 197, 94, 0.22)", "rgba(34, 197, 94, 0.36)"),
    },
    ChipTone.DANGER: {
        "dark": ("#F87171", "rgba(239, 68, 68, 0.20)", "rgba(239, 68, 68, 0.34)"),
        "light": ("#B91C1C", "rgba(239, 68, 68, 0.20)", "rgba(239, 68, 68, 0.34)"),
    },
}


class StatusChip(QLabel):
    """统一胶囊标签。

    参数页 RO/RW 权限标签、串口页连接状态标签、电源页在线状态标签
    均使用本组件，通过 ``tone`` 以颜色区分语义，并自适应明暗主题。
    """

    def __init__(self, text: str = "", tone: ChipTone = ChipTone.NEUTRAL, parent=None):
        super().__init__(text, parent)
        self._tone = tone
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(24)
        self.setMinimumWidth(42)
        setFont(self, 11, QFont.DemiBold)
        self.refreshTheme()

    def setTone(self, tone: ChipTone) -> None:
        self._tone = tone
        self.refreshTheme()

    def setOnline(self, online: bool) -> None:
        """连接状态便捷入口：在线→成功色，离线→危险色。"""
        self.setTone(ChipTone.SUCCESS if online else ChipTone.DANGER)

    def refreshTheme(self) -> None:
        dark = isDarkTheme()
        foreground, background, border = _CHIP_PALETTE[self._tone]["dark" if dark else "light"]
        self.setStyleSheet(
            f"""
            QLabel {{
                color: {foreground};
                background-color: {background};
                border: 1px solid {border};
                border-radius: 12px;
                padding-left: 10px;
                padding-right: 10px;
                font-weight: 700;
            }}
            """
        )
