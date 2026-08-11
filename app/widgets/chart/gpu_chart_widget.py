# -*- coding: utf-8 -*-
# -------------------------------
#  @Project : F4CP
#  @Time    : 2026 - 08-10 16:20
#  @FileName: gpu_chart_widget.py
#  @FileType: 图表组件文件，负责 GPU 曲线渲染与主题叠加层
#  @Software: PyCharm 2024.1.6 (Professional Edition)
#  @System  : Windows 11 23H2
#  @Author  : UF4
#  @Contact :
#  @Python  : 3.11
# -------------------------------

from __future__ import annotations

import array
import bisect
import logging
import time
from dataclasses import dataclass

from PyQt5.QtCore import QPoint, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QOpenGLBuffer,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLVertexArrayObject,
    QPainter,
    QPen,
    QVector2D,
    QVector4D,
)
from PyQt5.QtWidgets import QOpenGLWidget, QStackedLayout, QWidget
from qfluentwidgets import isDarkTheme

from app.widgets.chart.chart_model import ChartModel, ChartSnapshot

logger = logging.getLogger("F4CP.GpuChart")

GL_COLOR_BUFFER_BIT = 0x00004000
GL_BLEND = 0x0BE2
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_SCISSOR_TEST = 0x0C11
GL_LINE_STRIP = 0x0003
GL_FLOAT = 0x1406


@dataclass
class _CurveState:
    key: str
    name: str
    unit: str
    precision: int
    color: QColor
    line_width: float
    buffer: QOpenGLBuffer
    vertex_count: int = 0


class _ChartOverlay(QWidget):
    def __init__(self, owner: "GpuChartWidget", parent=None):
        super().__init__(parent)
        self._owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setObjectName("GpuChartOverlay")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            self._owner._paint_overlay(painter)
        finally:
            painter.end()


class _CurveGLWidget(QOpenGLWidget):
    def __init__(self, owner: "GpuChartWidget", parent=None):
        super().__init__(parent)
        self._owner = owner
        self.setMouseTracking(True)
        self.setObjectName("GpuChartGL")

    def initializeGL(self) -> None:
        self._owner._initialize_gl(self.context())

    def resizeGL(self, width: int, height: int) -> None:
        self._owner._geometry_dirty = True
        self._owner._overlay.update()

    def paintGL(self) -> None:
        self._owner._paint_gl()

    def mousePressEvent(self, event) -> None:
        self._owner._mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        self._owner._mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._owner._mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self._owner._mouseDoubleClickEvent(event)

    def wheelEvent(self, event) -> None:
        self._owner._wheelEvent(event)

    def leaveEvent(self, event) -> None:
        self._owner._setHoverVisible(False)
        self._owner._overlay.update()
        super().leaveEvent(event)


class GpuChartWidget(QWidget):
    """Realtime chart rendered by QOpenGLWidget + GLSL, with Qt overlay labels."""

    snapshotUpdated = pyqtSignal(object)

    def __init__(self, chart_model: ChartModel, parent=None):
        super().__init__(parent)
        self.setObjectName("GpuChartWidget")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMouseTracking(True)
        self.setMinimumSize(600, 360)

        self.chart_model = chart_model
        self.title = "Power Device Realtime Chart"
        self.latest_snapshot: ChartSnapshot | None = None
        self._snapshot_dirty = True
        self._geometry_dirty = True
        self._gl_ready = False
        self._dragging = False
        self._last_drag_x = 0
        self._hover_threshold_px = 12
        self._hover_info: dict | None = None
        self._curves: dict[str, _CurveState] = {}
        self._paint_ms_total = 0.0
        self._paint_count = 0
        self._gl = None
        self._program: QOpenGLShaderProgram | None = None
        self._vao = QOpenGLVertexArrayObject()

        self._curve_palette = (
            QColor(51, 140, 255),
            QColor(51, 217, 115),
            QColor(255, 166, 51),
            QColor(255, 77, 89),
            QColor(178, 115, 255),
            QColor(51, 217, 217),
            QColor(255, 230, 77),
            QColor(75, 85, 99),
        )

        self._gl_widget = _CurveGLWidget(self, self)
        self._overlay = _ChartOverlay(self, self)
        self._overlay.raise_()

        stack = QStackedLayout(self)
        stack.setStackingMode(QStackedLayout.StackAll)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.addWidget(self._gl_widget)
        stack.addWidget(self._overlay)

        self.refreshTheme()
        self._setHoverVisible(False)

    def set_title(self, title: str) -> None:
        self.title = title or "Power Device Realtime Chart"
        self._overlay.update()

    def paint_stats(self) -> float:
        if self._paint_count <= 0:
            return 0.0
        return self._paint_ms_total / self._paint_count

    def mark_data_dirty(self) -> None:
        self._snapshot_dirty = True

    def refreshTheme(self) -> None:
        dark = isDarkTheme()
        if dark:
            self._background = QColor("#313131")
            self._title_color = QColor(245, 247, 250)
            self._axis_color = QColor(165, 175, 190)
            self._grid_color = QColor(148, 163, 184, 58)
            self._legend_text_color = QColor(226, 232, 240)
            self._legend_bg = QColor(17, 24, 39, 190)
            self._legend_border = QColor(255, 255, 255, 26)
            self._cross_color = QColor(255, 255, 255, 168)
            self._axis_fill = QColor(255, 255, 255, 12)
            self._tooltip_bg = QColor(15, 23, 42, 220)
        else:
            self._background = QColor("#fdfdfd")
            self._title_color = QColor(17, 24, 39)
            self._axis_color = QColor(71, 85, 105)
            self._grid_color = QColor(51, 65, 85, 62)
            self._legend_text_color = QColor(15, 23, 42)
            self._legend_bg = QColor(255, 255, 255, 226)
            self._legend_border = QColor(15, 23, 42, 28)
            self._cross_color = QColor(15, 23, 42, 118)
            self._axis_fill = QColor(15, 23, 42, 10)
            self._tooltip_bg = QColor(255, 255, 255, 240)

        self.setStyleSheet("""
            QWidget#GpuChartWidget {
                background: transparent;
                border: none;
            }
        """)
        self._overlay.update()
        if self._gl_ready:
            self._gl_widget.update()

    def update(self, *args, **kwargs) -> None:
        self.update_plot()
        self._gl_widget.update()
        self._overlay.update()
        super().update(*args, **kwargs)

    def resizeEvent(self, event) -> None:
        self._geometry_dirty = True
        self.mark_data_dirty()
        self.update_plot(force=True)
        super().resizeEvent(event)

    def update_plot(self, force: bool = False) -> None:
        if not force and not self._snapshot_dirty and self.latest_snapshot is not None:
            return

        width = max(1, self._plot_rect_width())
        snapshot = self.chart_model.build_snapshot_for_width(width)
        self.latest_snapshot = snapshot
        self._snapshot_dirty = False
        self._geometry_dirty = True
        self.snapshotUpdated.emit(snapshot)
        self._overlay.update()
        if self._gl_ready:
            self._gl_widget.update()

    def _initialize_gl(self, context) -> None:
        if self._gl_ready:
            return

        try:
            self._gl = context.versionFunctions() if context is not None else None
            if self._gl is None:
                logger.warning("OpenGL context functions unavailable, chart will stay blank.")
                return

            self._program = QOpenGLShaderProgram(self)
            if not self._program.addShaderFromSourceCode(QOpenGLShader.Vertex, self._vertex_shader()):
                raise RuntimeError(self._program.log())
            if not self._program.addShaderFromSourceCode(QOpenGLShader.Fragment, self._fragment_shader()):
                raise RuntimeError(self._program.log())
            self._program.bindAttributeLocation("a_position", 0)
            if not self._program.link():
                raise RuntimeError(self._program.log())

            if not self._vao.create():
                logger.warning("OpenGL VAO creation failed, continuing without VAO.")
            else:
                self._vao.bind()
                self._vao.release()

            self._gl_ready = True
            self._geometry_dirty = True
            self._upload_geometry()
            logger.info("GPU chart renderer initialized (QOpenGLWidget + GLSL).")
        except Exception as exc:
            self._gl_ready = False
            self._program = None
            self._gl = None
            logger.warning(f"GPU chart renderer initialization failed: {exc}")

    def _paint_gl(self) -> None:
        start = time.perf_counter()
        try:
            if self._gl is None:
                return

            width = max(1, self._gl_widget.width())
            height = max(1, self._gl_widget.height())
            self._gl.glViewport(0, 0, width, height)
            self._gl.glClearColor(
                self._background.redF(),
                self._background.greenF(),
                self._background.blueF(),
                1.0,
            )
            self._gl.glClear(GL_COLOR_BUFFER_BIT)

            if self.latest_snapshot is None:
                return

            if self._geometry_dirty:
                self._upload_geometry()

            plot = self._plot_rect()
            if plot.width() <= 1 or plot.height() <= 1:
                return

            if self._program is None:
                return

            self._gl.glEnable(GL_BLEND)
            self._gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            self._gl.glEnable(GL_SCISSOR_TEST)
            self._gl.glScissor(
                int(plot.left()),
                int(height - (plot.top() + plot.height())),
                int(plot.width()),
                int(plot.height()),
            )

            program_bound = False
            vao_bound = False
            try:
                program_bound = self._program.bind()
                if not program_bound:
                    return

                self._program.setUniformValue("u_plotMin", QVector2D(*self._plot_min_ndc()))
                self._program.setUniformValue("u_plotMax", QVector2D(*self._plot_max_ndc()))
                self._program.enableAttributeArray(0)

                if self._vao.isCreated():
                    self._vao.bind()
                    vao_bound = True

                for curve in self.latest_snapshot.curves:
                    state = self._curves.get(curve.key)
                    if state is None or state.vertex_count < 2:
                        continue
                    if not state.buffer.bind():
                        continue
                    try:
                        self._program.setAttributeBuffer(0, GL_FLOAT, 0, 2, 0)
                        self._program.setUniformValue("u_color", QVector4D(*self._qcolor_to_rgba(state.color)))
                        self._gl.glLineWidth(max(1.0, state.line_width))
                        self._gl.glDrawArrays(GL_LINE_STRIP, 0, state.vertex_count)
                    finally:
                        state.buffer.release()
            finally:
                if vao_bound:
                    self._vao.release()
                if program_bound:
                    self._program.release()
                self._gl.glDisable(GL_SCISSOR_TEST)
                self._gl.glDisable(GL_BLEND)
        finally:
            self._paint_ms_total += (time.perf_counter() - start) * 1000.0
            self._paint_count += 1

    def _upload_geometry(self) -> None:
        if self._gl is None or self._program is None or self.latest_snapshot is None:
            return

        active_keys: set[str] = set()
        for index, curve in enumerate(self.latest_snapshot.curves):
            active_keys.add(curve.key)
            state = self._curves.get(curve.key)
            if state is None:
                state = _CurveState(
                    key=curve.key,
                    name=curve.name,
                    unit=curve.unit,
                    precision=curve.precision,
                    color=self._curveColor(curve.key, index),
                    line_width=self._lineWidth(curve.key),
                    buffer=QOpenGLBuffer(QOpenGLBuffer.VertexBuffer),
                )
                if not state.buffer.create():
                    raise RuntimeError(f"failed to create VBO for {curve.key}")
                state.buffer.setUsagePattern(QOpenGLBuffer.StreamDraw)
                self._curves[curve.key] = state
            else:
                state.name = curve.name
                state.unit = curve.unit
                state.precision = curve.precision
                state.color = self._curveColor(curve.key, index)
                state.line_width = self._lineWidth(curve.key)

            coords = array.array("f")
            for point in curve.points:
                coords.append(float(point.gl_x))
                coords.append(float(point.gl_y))

            vertex_bytes = coords.tobytes()
            state.buffer.bind()
            state.buffer.allocate(len(vertex_bytes))
            if vertex_bytes:
                state.buffer.write(0, vertex_bytes, len(vertex_bytes))
            state.buffer.release()
            state.vertex_count = len(coords) // 2

        for key in list(self._curves):
            if key not in active_keys:
                state = self._curves.pop(key)
                try:
                    state.buffer.destroy()
                except Exception:
                    pass

        self._geometry_dirty = False

    def _mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._beginDrag(event.pos().x())
            event.accept()
            return
        event.ignore()

    def _mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self._dragTo(event.pos().x())
            event.accept()
            return
        self._updateHoverFromPos(event.pos(), event)
        event.accept()

    def _mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._dragging:
            self._endDrag()
            event.accept()
            return
        event.ignore()

    def _mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._resetTimeOffset()
            event.accept()
            return
        event.ignore()

    def _wheelEvent(self, event) -> None:
        self._zoomTime(event.angleDelta().y())
        event.accept()

    def _plot_rect(self) -> QRectF:
        width = max(1, self._gl_widget.width())
        height = max(1, self._gl_widget.height())
        left = 48.0
        top = 16.0
        right = 16.0
        bottom = 36.0
        return QRectF(left, top, max(1.0, width - left - right), max(1.0, height - top - bottom))

    def _plot_rect_width(self) -> int:
        return int(max(1.0, self._plot_rect().width()))

    def _plot_min_ndc(self) -> tuple[float, float]:
        plot = self._plot_rect()
        width = max(1.0, float(self._gl_widget.width()))
        height = max(1.0, float(self._gl_widget.height()))
        x_min = (plot.left() / width) * 2.0 - 1.0
        y_max = 1.0 - (plot.top() / height) * 2.0
        return (x_min, y_max)

    def _plot_max_ndc(self) -> tuple[float, float]:
        plot = self._plot_rect()
        width = max(1.0, float(self._gl_widget.width()))
        height = max(1.0, float(self._gl_widget.height()))
        x_max = ((plot.left() + plot.width()) / width) * 2.0 - 1.0
        y_min = 1.0 - ((plot.top() + plot.height()) / height) * 2.0
        return (x_max, y_min)

    def _beginDrag(self, x: int) -> None:
        self._dragging = True
        self._last_drag_x = int(x)
        self._gl_widget.setCursor(Qt.ClosedHandCursor)
        self._setHoverVisible(False)

    def _dragTo(self, x: int) -> None:
        plot = self._plot_rect()
        dx = int(x) - self._last_drag_x
        self._last_drag_x = int(x)
        seconds_per_px = self.chart_model.time_window_sec / max(1.0, plot.width())
        self.chart_model.pan_time(-dx * seconds_per_px)
        self.mark_data_dirty()
        self.update_plot(force=True)
        self._setHoverVisible(False)

    def _endDrag(self) -> None:
        self._dragging = False
        self._gl_widget.setCursor(Qt.ArrowCursor)

    def _resetTimeOffset(self) -> None:
        self.chart_model.reset_time_offset()
        self.mark_data_dirty()
        self.update_plot(force=True)

    def _zoomTime(self, wheel_delta: int) -> None:
        self.chart_model.zoom_time_window(0.8 if wheel_delta > 0 else 1.25)
        self.mark_data_dirty()
        self.update_plot(force=True)

    def _updateHoverFromPos(self, pos, event=None) -> None:
        if self._dragging or self.latest_snapshot is None:
            self._setHoverVisible(False)
            return

        plot = self._plot_rect()
        if not plot.contains(pos):
            self._setHoverVisible(False)
            return

        x_value = self._x_value_from_pos(pos.x())
        y_value = self._y_value_from_pos(pos.y())
        self._updateHover(x_value, y_value, pos)

    def _x_value_from_pos(self, x: float) -> float:
        snapshot = self.latest_snapshot
        if snapshot is None:
            return 0.0
        plot = self._plot_rect()
        ratio = max(0.0, min(1.0, (x - plot.left()) / max(1.0, plot.width())))
        return snapshot.x_range.minimum + snapshot.x_range.span * ratio

    def _y_value_from_pos(self, y: float) -> float:
        snapshot = self.latest_snapshot
        if snapshot is None:
            return 0.0
        plot = self._plot_rect()
        ratio = max(0.0, min(1.0, (y - plot.top()) / max(1.0, plot.height())))
        return snapshot.y_range.maximum - snapshot.y_range.span * ratio

    def _updateHover(self, x_value: float, y_value: float, pos) -> None:
        snapshot = self.latest_snapshot
        if snapshot is None:
            self._setHoverVisible(False)
            return

        target_time = x_value
        best = None
        best_dist2 = self._hover_threshold_px * self._hover_threshold_px
        for curve in snapshot.curves:
            if not curve.points:
                continue
            times = [point.raw_x for point in curve.points]
            insert_at = bisect.bisect_left(times, target_time)
            candidate_indexes = range(max(0, insert_at - 2), min(len(curve.points), insert_at + 3))
            for index in candidate_indexes:
                point = curve.points[index]
                px, py = self._point_to_pixel(point.gl_x, point.gl_y)
                dx = px - pos.x()
                dy = py - pos.y()
                dist2 = dx * dx + dy * dy
                if dist2 <= best_dist2:
                    best_dist2 = dist2
                    best = (curve, point, px, py)

        if best is None:
            self._setHoverVisible(False)
            return

        curve, hovered_point, px, py = best
        self._hover_info = {
            "curve": curve,
            "px": px,
            "py": py,
            "text": f"{curve.name}: {hovered_point.raw_y:.{curve.precision}f}{curve.unit}",
        }
        self._overlay.update()

    def _point_to_pixel(self, gl_x: float, gl_y: float) -> tuple[float, float]:
        plot = self._plot_rect()
        x = plot.left() + (gl_x + 1.0) * 0.5 * plot.width()
        y = plot.top() + (1.0 - (gl_y + 1.0) * 0.5) * plot.height()
        return (x, y)

    def _setHoverVisible(self, visible: bool) -> None:
        if not visible:
            self._hover_info = None
        self._overlay.update()

    def _paint_overlay(self, painter: QPainter) -> None:
        plot = self._plot_rect()
        if plot.width() <= 1 or plot.height() <= 1:
            return

        painter.setPen(Qt.NoPen)
        painter.setBrush(Qt.transparent)

        title_font = QFont("Microsoft YaHei", 10, QFont.Bold)
        axis_font = QFont("Consolas", 8)
        legend_font = QFont("Microsoft YaHei", 9)

        painter.setFont(title_font)
        painter.setPen(self._title_color)
        painter.drawText(12, 24, self.title)

        painter.setPen(QPen(self._grid_color, 1, Qt.DotLine))
        for index in range(11):
            x = round(plot.left() + plot.width() * index / 10.0)
            painter.drawLine(x, int(plot.top()), x, int(plot.bottom()))
        for index in range(9):
            y = round(plot.top() + plot.height() * index / 8.0)
            painter.drawLine(int(plot.left()), y, int(plot.right()), y)

        painter.setPen(QPen(self._axis_fill, 1))
        painter.drawRect(plot.adjusted(0, 0, -1, -1))

        painter.setFont(axis_font)
        painter.setPen(self._axis_color)
        snapshot = self.latest_snapshot
        if snapshot is not None:
            for index in range(6):
                ratio = index / 5.0
                x = plot.left() + plot.width() * ratio
                value = snapshot.x_range.minimum + snapshot.x_range.span * ratio
                text = f"{value - snapshot.x_range.maximum:.1f}s"
                painter.drawText(QRectF(x - 28, plot.bottom() + 4, 56, 12), Qt.AlignCenter, text)

            for index in range(5):
                ratio = index / 4.0
                y = plot.top() + plot.height() * ratio
                value = snapshot.y_range.maximum - snapshot.y_range.span * ratio
                painter.drawText(QRectF(2, y - 7, 40, 14), Qt.AlignRight | Qt.AlignVCenter, f"{value:.2f}")

        legend_items = []
        if snapshot is not None:
            for index, curve in enumerate(snapshot.curves):
                if not curve.points:
                    continue
                legend_items.append(
                    (
                        self._curveColor(curve.key, index),
                        f"{curve.name}: {curve.points[-1].raw_y:.{curve.precision}f}{curve.unit}",
                    )
                )

        if legend_items:
            painter.setFont(legend_font)
            metrics = QFontMetrics(legend_font)
            text_width = max(metrics.horizontalAdvance(text) for _, text in legend_items)
            box_width = text_width + 30
            box_height = 8 + len(legend_items) * 18
            box_x = int(plot.right() - box_width - 8)
            box_y = int(plot.top() + 8)
            box = QRectF(box_x, box_y, box_width, box_height)
            painter.setPen(QPen(self._legend_border, 1))
            painter.setBrush(self._legend_bg)
            painter.drawRoundedRect(box, 8, 8)
            for idx, (color, text) in enumerate(legend_items):
                row_y = box_y + 20 + idx * 18
                painter.setPen(color)
                painter.drawText(box_x + 12, row_y, "■")
                painter.setPen(self._legend_text_color)
                painter.drawText(box_x + 28, row_y, text)

        if self._hover_info:
            px = self._hover_info["px"]
            py = self._hover_info["py"]
            painter.setPen(QPen(self._cross_color, 1))
            painter.drawLine(int(px), int(plot.top()), int(px), int(plot.bottom()))
            painter.drawLine(int(plot.left()), int(py), int(plot.right()), int(py))
            painter.setBrush(self._title_color if isDarkTheme() else self._axis_color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPoint(int(px), int(py)), 4, 4)

            tooltip_font = QFont("Consolas", 8)
            painter.setFont(tooltip_font)
            metrics = QFontMetrics(tooltip_font)
            text = self._hover_info["text"]
            text_width = metrics.horizontalAdvance(text)
            tip_width = text_width + 20
            tip_height = 24
            tip_x = int(px + 12)
            tip_y = int(py - tip_height - 12)
            if tip_x + tip_width > self.width() - 8:
                tip_x = int(px - tip_width - 12)
            if tip_y < 8:
                tip_y = int(py + 12)
            tip_rect = QRectF(tip_x, tip_y, tip_width, tip_height)
            painter.setPen(QPen(self._legend_border, 1))
            painter.setBrush(self._tooltip_bg)
            painter.drawRoundedRect(tip_rect, 7, 7)
            painter.setPen(self._legend_text_color if isDarkTheme() else self._title_color)
            painter.drawText(tip_rect.adjusted(10, 0, -10, 0), Qt.AlignVCenter | Qt.AlignLeft, text)

        painter.setPen(self._axis_color)
        painter.setFont(axis_font)
        painter.drawText(QRectF(6, plot.top() + 4, 36, 16), Qt.AlignRight | Qt.AlignVCenter, "值")
        painter.drawText(QRectF(plot.right() - 82, self.height() - 24, 76, 16), Qt.AlignRight | Qt.AlignVCenter, "时间 (s)")

    @staticmethod
    def _qcolor_to_rgba(color: QColor) -> tuple[float, float, float, float]:
        return (color.redF(), color.greenF(), color.blueF(), color.alphaF())

    def _curveColor(self, key: str, index: int) -> QColor:
        channel = self.chart_model.data_hub.get_channel(key)
        if channel is not None and channel.config.color:
            return QColor(*channel.config.color)
        return self._curve_palette[index % len(self._curve_palette)]

    def _lineWidth(self, key: str) -> float:
        channel = self.chart_model.data_hub.get_channel(key)
        if channel is None:
            return 2.0
        return float(channel.config.line_width)

    @staticmethod
    def _vertex_shader() -> str:
        return """
            attribute vec2 a_position;
            uniform vec2 u_plotMin;
            uniform vec2 u_plotMax;

            void main() {
                vec2 normalized = (a_position + vec2(1.0, 1.0)) * 0.5;
                vec2 clip = mix(u_plotMin, u_plotMax, normalized);
                gl_Position = vec4(clip, 0.0, 1.0);
            }
        """

    @staticmethod
    def _fragment_shader() -> str:
        return """
            uniform vec4 u_color;

            void main() {
                gl_FragColor = u_color;
            }
        """


PyQtGraphChartWidget = GpuChartWidget
