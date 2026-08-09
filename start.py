# -*- coding: utf-8 -*-
# -------------------------------
#  @Project : F4CP
#  @Time    : 2026 - 01-08 12:30
#  @FileName: start.py
#  @FileType: 应用入口文件，负责创建主窗口并启动 Qt 事件循环
#  @Software: PyCharm 2024.1.6 (Professional Edition)
#  @System  : Windows 11 23H2
#  @Author  : UF4
#  @Contact :
#  @Python  : 3.11
# -------------------------------

import sys
from PyQt5.QtGui import QCloseEvent
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from config import get_logger,cfg
from app.manager import loadSavedFont

logger = get_logger("Bootstrap")

from app.window import Window

class Application(Window):
    def __init__(self):
        super().__init__()
        self.setFixedSize(1500,1200)

    def close(self):
        logger.warning("Application closed")
        super().close()

    def closeEvent(self, event: QCloseEvent):
        super().closeEvent(event)

if __name__ == "__main__":
    logger.info("main is running")
    if cfg.highDpiScaling.value:
        logger.info("highDpiScaling is running")
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling)
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)

    logger.info("Application started")
    try:
        app = QApplication(sys.argv)
        loadSavedFont(app)  # 加载字体
        w = Application()
        w.show()
        sys.exit(app.exec_())
    except Exception as e:
        logger.error(e)
        sys.exit(-1)
