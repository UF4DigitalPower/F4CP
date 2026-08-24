# -*- coding: utf-8 -*-
"""ADP capture/training session.

The page communicates with this session only through request/result events.
Serial I/O and CSV persistence run in a worker thread so the Qt UI thread never
owns a blocking serial operation or a high-rate parser loop.
"""

from __future__ import annotations

import csv
import queue
import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from PyQt5.QtCore import QCoreApplication, QEvent, QProcess, QTimer, QObject

from app.protocol.uf4com import (
    Uf4Command,
    Uf4Flag,
    Uf4FrameParser,
    build_frame,
    encode_tv,
    iter_tv_items,
)
from app.session.page_device.other_device import listSerialPorts

try:
    import serial
except Exception:  # pragma: no cover - optional until capture is used
    serial = None


STREAM_IDS = (0x11, 0x0A, 0x0C, 0x0B, 0x0D, 0x2A, 0x2D)
CAPTURE_MAX_READ_BYTES = 4096
CAPTURE_MAX_FRAMES_PER_POLL = 128
CAPTURE_PROGRESS_INTERVAL_S = 0.25
CAPTURE_MAX_ROWS = 200000
CSV_FIELDS = (
    "episode",
    "step",
    "vref_v",
    "vin_v",
    "vout_v",
    "iin_a",
    "iout_a",
    "iref_applied_a",
)


class AdpRequestAction(str, Enum):
    REFRESH_PORTS = "refresh_ports"
    START_CAPTURE = "start_capture"
    STOP_CAPTURE = "stop_capture"
    START_TRAINING = "start_training"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True)
class AdpCaptureConfig:
    port: str
    baudrate: int
    dataset: Path


@dataclass(frozen=True)
class AdpTrainingConfig:
    dataset: Path
    ilimit: float
    epochs: int
    validation_ratio: float
    seed: int
    output: Path
    report: Path


def _new_event_type() -> QEvent.Type:
    return QEvent.Type(QEvent.registerEventType())


class _AdpEvent(QEvent):
    EVENT_TYPE = _new_event_type()

    def __init__(self, payload=None):
        super().__init__(self.EVENT_TYPE)
        self.payload = payload


class AdpRequestEvent(QEvent):
    EVENT_TYPE = _new_event_type()

    def __init__(self, action: AdpRequestAction, payload=None):
        super().__init__(self.EVENT_TYPE)
        self.action = action
        self.payload = payload


@dataclass(frozen=True)
class AdpPortsPayload:
    ports: tuple[str, ...]


class AdpPortsEvent(_AdpEvent):
    EVENT_TYPE = _new_event_type()

    def __init__(self, ports: list[str] | tuple[str, ...]):
        super().__init__(AdpPortsPayload(tuple(ports)))


@dataclass(frozen=True)
class AdpLogPayload:
    text: str
    level: str = "info"


class AdpLogEvent(_AdpEvent):
    EVENT_TYPE = _new_event_type()

    def __init__(self, text: str, level: str = "info"):
        super().__init__(AdpLogPayload(text, level))


@dataclass(frozen=True)
class AdpStatePayload:
    state: str
    port: str = ""
    rows: int = 0
    dropped_frames: int = 0


class AdpStateEvent(_AdpEvent):
    EVENT_TYPE = _new_event_type()

    def __init__(
        self,
        state: str,
        port: str = "",
        rows: int = 0,
        dropped_frames: int = 0,
    ):
        super().__init__(AdpStatePayload(state, port, rows, dropped_frames))


@dataclass(frozen=True)
class AdpCaptureSavedPayload:
    path: Path
    rows: int


class AdpCaptureSavedEvent(_AdpEvent):
    EVENT_TYPE = _new_event_type()

    def __init__(self, path: Path, rows: int):
        super().__init__(AdpCaptureSavedPayload(path, rows))


@dataclass(frozen=True)
class AdpTrainingFinishedPayload:
    success: bool
    output: Path
    report: Path
    message: str


class AdpTrainingFinishedEvent(_AdpEvent):
    EVENT_TYPE = _new_event_type()

    def __init__(
        self,
        success: bool,
        output: Path,
        report: Path,
        message: str,
    ):
        super().__init__(
            AdpTrainingFinishedPayload(success, output, report, message)
        )


class AdpErrorEvent(_AdpEvent):
    EVENT_TYPE = _new_event_type()

    def __init__(self, text: str):
        super().__init__(AdpLogPayload(text, "error"))


@dataclass(frozen=True)
class _WorkerMessage:
    kind: str
    payload: object


class _CaptureWorker(threading.Thread):
    """Thread-owned serial reader and dataset writer."""

    def __init__(self, event_queue: queue.Queue[_WorkerMessage]):
        super().__init__(name="F4CP-ADP-Capture", daemon=True)
        self._event_queue = event_queue
        self._commands: queue.Queue[tuple[str, object | None]] = queue.Queue()
        self._stop_requested = threading.Event()
        self._capturing = threading.Event()
        self._port = None
        self._config: AdpCaptureConfig | None = None
        self._parser = Uf4FrameParser()
        self._rows: list[dict[str, object]] = []
        self._step = 0
        self._last_progress = 0.0
        self._dropped_frames = 0

    def command(self, action: str, payload=None) -> None:
        self._commands.put((action, payload))

    def run(self) -> None:
        while not self._stop_requested.is_set():
            self._consume_commands()
            if self._port is not None:
                self._poll_port()
            else:
                time.sleep(0.005)
        self._close_capture(save=False)

    def _consume_commands(self) -> None:
        while True:
            try:
                action, payload = self._commands.get_nowait()
            except queue.Empty:
                return
            if action == "start":
                self._start_capture(payload)
            elif action == "stop":
                self._close_capture(save=True)
            elif action == "shutdown":
                self._close_capture(save=False)
                self._stop_requested.set()
                return

    @property
    def is_capturing(self) -> bool:
        return self._capturing.is_set()

    def _post(self, kind: str, payload: object) -> None:
        self._event_queue.put(_WorkerMessage(kind, payload))

    def _start_capture(self, config: AdpCaptureConfig) -> None:
        self._close_capture(save=False)
        if serial is None:
            self._post("error", AdpLogPayload("缺少 pyserial，无法打开串口", "error"))
            return
        if not config.port or config.port == "未发现串口":
            self._post("error", AdpLogPayload("请先选择有效串口", "error"))
            return
        try:
            self._port = serial.Serial(
                port=config.port,
                baudrate=config.baudrate,
                timeout=0,
                write_timeout=0.25,
            )
            self._port.reset_input_buffer()
            self._config = config
            self._parser = Uf4FrameParser()
            self._rows = []
            self._step = 0
            self._dropped_frames = 0
            self._last_progress = time.monotonic()
            self._capturing.set()
            payload = b"".join(encode_tv(item, 0) for item in STREAM_IDS)
            self._port.write(
                build_frame(
                    Uf4Command.STREAM_START_REQ,
                    1,
                    payload,
                    int(Uf4Flag.ACK_REQ),
                )
            )
            self._post("state", AdpStatePayload("capturing", config.port, 0, 0))
            self._post(
                "log",
                AdpLogPayload(
                    f"STREAM_START -> {config.port} ({len(STREAM_IDS)} fields)"
                ),
            )
            if config.baudrate < 460800:
                self._post(
                    "log",
                    AdpLogPayload(
                        "警告: 波特率低于 460800，设备 1 kHz 流帧可能产生串口积压，建议使用 921600",
                        "warning",
                    ),
                )
        except Exception as exc:
            self._close_capture(save=False)
            self._post("error", AdpLogPayload(f"打开串口失败: {exc}", "error"))

    def _poll_port(self) -> None:
        try:
            available = int(self._port.in_waiting)
            if available <= 0:
                return
            data = self._port.read(min(available, CAPTURE_MAX_READ_BYTES))
            frames = self._parser.feed(data)
            processed = 0
            for frame in frames:
                if int(frame.cmd) != int(Uf4Command.STREAM_DATA):
                    continue
                if processed >= CAPTURE_MAX_FRAMES_PER_POLL:
                    self._dropped_frames += 1
                    continue
                self._accept_frame(frame.data)
                processed += 1
                if self._port is None:
                    break
            now = time.monotonic()
            if now - self._last_progress >= CAPTURE_PROGRESS_INTERVAL_S:
                self._post(
                    "state",
                    AdpStatePayload(
                        "capturing",
                        self._config.port if self._config else "",
                        len(self._rows),
                        self._dropped_frames,
                    ),
                )
                self._last_progress = now
        except Exception as exc:
            self._post("error", AdpLogPayload(f"串口读取失败: {exc}", "error"))
            self._close_capture(save=True)

    def _accept_frame(self, payload: bytes) -> None:
        values = {
            item.id: item.value
            for item in iter_tv_items(payload, strict=False)
            if item.value is not None
        }
        if not all(item in values for item in STREAM_IDS):
            return
        if len(self._rows) >= CAPTURE_MAX_ROWS:
            self._post(
                "log",
                AdpLogPayload(
                    f"已达到采样上限 {CAPTURE_MAX_ROWS}，正在保存",
                    "warning",
                ),
            )
            self._close_capture(save=True)
            return
        self._step += 1
        self._rows.append(
            {
                "episode": 0,
                "step": self._step,
                "vref_v": values[0x11] / 100.0,
                "vin_v": values[0x0A] / 100.0,
                "vout_v": values[0x0C] / 100.0,
                "iin_a": values[0x0B] / 100.0,
                "iout_a": values[0x0D] / 100.0,
                "iref_applied_a": values[0x2A] / 100.0,
            }
        )

    def _close_capture(self, save: bool) -> None:
        config = self._config
        port = self._port
        self._port = None
        self._config = None
        self._capturing.clear()
        if port is not None:
            try:
                port.write(
                    build_frame(
                        Uf4Command.STREAM_STOP_REQ,
                        2,
                        b"",
                        int(Uf4Flag.ACK_REQ),
                    )
                )
            except Exception as exc:
                self._post(
                    "log",
                    AdpLogPayload(f"STREAM_STOP 发送失败: {exc}", "warning"),
                )
            try:
                port.close()
            except Exception:
                pass
        if save and config is not None and self._rows:
            try:
                config.dataset.parent.mkdir(parents=True, exist_ok=True)
                with config.dataset.open(
                    "w", newline="", encoding="utf-8"
                ) as handle:
                    writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
                    writer.writeheader()
                    writer.writerows(self._rows)
                self._post(
                    "saved",
                    AdpCaptureSavedPayload(config.dataset, len(self._rows)),
                )
            except Exception as exc:
                self._post(
                    "error",
                    AdpLogPayload(f"训练数据保存失败: {exc}", "error"),
                )
        if config is not None:
            self._post(
                "state",
                AdpStatePayload(
                    "idle",
                    config.port,
                    len(self._rows),
                    self._dropped_frames,
                ),
            )


class AdpTrainingSession(QObject):
    """Event-driven coordinator for capture and offline training."""

    def __init__(self, event_receiver: QObject, parent=None):
        super().__init__(parent)
        self._event_receiver = event_receiver
        self._worker_events: queue.Queue[_WorkerMessage] = queue.Queue()
        self._worker = _CaptureWorker(self._worker_events)
        self._worker.start()
        self._worker_event_timer = QTimer(self)
        self._worker_event_timer.setInterval(10)
        self._worker_event_timer.timeout.connect(self._drain_worker_events)
        self._worker_event_timer.start()
        self._process: QProcess | None = None
        self._pending_training: AdpTrainingConfig | None = None
        self._shutdown = False

    def _publish(self, event: QEvent) -> None:
        QCoreApplication.postEvent(self._event_receiver, event)

    def customEvent(self, event: QEvent) -> None:
        if isinstance(event, AdpRequestEvent):
            self._handle_request(event.action, event.payload)
        else:
            super().customEvent(event)

    def _drain_worker_events(self) -> None:
        for _ in range(64):
            try:
                message = self._worker_events.get_nowait()
            except queue.Empty:
                return
            self._handle_worker_message(message)

    def _handle_worker_message(self, message: _WorkerMessage) -> None:
        if message.kind == "saved":
            payload = message.payload
            assert isinstance(payload, AdpCaptureSavedPayload)
            event = AdpCaptureSavedEvent(payload.path, payload.rows)
            self._publish(event)
            if self._pending_training is not None:
                config = self._pending_training
                self._pending_training = None
                self._start_training(config)
            return
        if message.kind == "state":
            payload = message.payload
            assert isinstance(payload, AdpStatePayload)
            event = AdpStateEvent(
                payload.state,
                payload.port,
                payload.rows,
                payload.dropped_frames,
            )
            if payload.state == "idle" and self._process is not None:
                return
            self._publish(event)
            return
        if message.kind == "log":
            payload = message.payload
            assert isinstance(payload, AdpLogPayload)
            self._publish(AdpLogEvent(payload.text, payload.level))
            return
        if message.kind == "error":
            payload = message.payload
            assert isinstance(payload, AdpLogPayload)
            self._publish(AdpErrorEvent(payload.text))
            return

        self._publish(AdpErrorEvent(f"未知采集线程消息: {message.kind}"))

    def _handle_worker_event(self, event: QEvent) -> None:
        """Compatibility shim for callers from older local builds."""
        if isinstance(event, AdpCaptureSavedEvent):
            self._publish(event)
            if self._pending_training is not None:
                config = self._pending_training
                self._pending_training = None
                self._start_training(config)
            return
        if isinstance(event, AdpStateEvent):
            if event.payload.state == "idle" and self._process is not None:
                return
            self._publish(event)
            return
        if isinstance(event, (AdpPortsEvent, AdpLogEvent, AdpStateEvent, AdpErrorEvent)):
            self._publish(event)

    def _handle_request(self, action: AdpRequestAction, payload) -> None:
        if action == AdpRequestAction.REFRESH_PORTS:
            try:
                self._publish(AdpPortsEvent(listSerialPorts() or []))
            except Exception as exc:
                self._publish(AdpErrorEvent(f"串口扫描失败: {exc}"))
        elif action == AdpRequestAction.START_CAPTURE:
            if self._shutdown:
                return
            if self._process is not None:
                self._publish(AdpErrorEvent("训练进程正在运行，请稍候"))
                return
            self._pending_training = None
            self._worker.command("start", payload)
        elif action == AdpRequestAction.STOP_CAPTURE:
            if self._shutdown:
                return
            self._pending_training = None
            self._worker.command("stop")
        elif action == AdpRequestAction.START_TRAINING:
            if self._shutdown:
                return
            self._start_or_queue_training(payload)
        elif action == AdpRequestAction.SHUTDOWN:
            self.shutdown()

    def _start_or_queue_training(self, config: AdpTrainingConfig) -> None:
        if self._process is not None:
            self._publish(AdpErrorEvent("训练进程正在运行，请稍候"))
            return
        if self._worker.is_alive() and self._worker.is_capturing:
            self._pending_training = config
            self._worker.command("stop")
            self._publish(AdpLogEvent("正在停止采集并保存数据，然后开始训练"))
            return
        self._start_training(config)

    def _trainer_command(self) -> tuple[str, list[str], Path]:
        script = Path(__file__).parents[2] / "tools" / "adp_offline_train.py"
        if getattr(sys, "frozen", False):
            return sys.executable, ["--adp-train"], Path(sys.executable).resolve().parent
        return sys.executable, [str(script)], script.parent.parent

    def _start_training(self, config: AdpTrainingConfig) -> None:
        if not config.dataset.exists():
            self._publish(AdpErrorEvent("请先采集或选择 CSV 数据集"))
            return
        program, prefix, workdir = self._trainer_command()
        if not getattr(sys, "frozen", False):
            script = Path(prefix[0])
            if not script.exists():
                self._publish(AdpErrorEvent(f"训练器不存在: {script}"))
                return
        try:
            config.output.parent.mkdir(parents=True, exist_ok=True)
            args = prefix + [
                "--dataset",
                str(config.dataset),
                "--ilimit",
                str(config.ilimit),
                "--epochs",
                str(config.epochs),
                "--validation-ratio",
                str(config.validation_ratio),
                "--seed",
                str(config.seed),
                "--output",
                str(config.output),
                "--report",
                str(config.report),
            ]
            self._process = QProcess(self)
            self._process.setWorkingDirectory(str(workdir))
            self._process.setProgram(program)
            self._process.setArguments(args)
            self._process.readyReadStandardOutput.connect(
                self._on_training_stdout
            )
            self._process.readyReadStandardError.connect(self._on_training_stderr)
            self._process.finished.connect(
                lambda code, _status: self._on_training_finished(
                    int(code), config
                )
            )
            self._process.start()
            self._publish(AdpStateEvent("training"))
            self._publish(
                AdpLogEvent("启动离线训练: " + " ".join([program] + args))
            )
        except Exception as exc:
            self._process = None
            self._publish(AdpErrorEvent(f"训练启动失败: {exc}"))

    def _on_training_stdout(self) -> None:
        if self._process is not None:
            text = bytes(self._process.readAllStandardOutput()).decode(
                errors="replace"
            ).strip()
            if text:
                self._publish(AdpLogEvent(text))

    def _on_training_stderr(self) -> None:
        if self._process is not None:
            text = bytes(self._process.readAllStandardError()).decode(
                errors="replace"
            ).strip()
            if text:
                self._publish(AdpLogEvent(text, "warning"))

    def _on_training_finished(
        self,
        exit_code: int,
        config: AdpTrainingConfig,
    ) -> None:
        success = exit_code == 0
        self._process = None
        message = "训练完成" if success else f"训练失败，退出码 {exit_code}"
        self._publish(
            AdpTrainingFinishedEvent(
                success,
                config.output,
                config.report,
                message,
            )
        )
        self._publish(AdpStateEvent("idle"))

    def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        self._pending_training = None
        self._worker_event_timer.stop()
        if self._process is not None:
            self._process.kill()
            self._process.waitForFinished(1000)
            self._process = None
        if self._worker.is_alive():
            self._worker.command("shutdown")
            self._worker.join(timeout=1.5)


__all__ = [
    "AdpCaptureConfig",
    "AdpCaptureSavedEvent",
    "AdpErrorEvent",
    "AdpLogEvent",
    "AdpPortsEvent",
    "AdpRequestAction",
    "AdpRequestEvent",
    "AdpStateEvent",
    "AdpTrainingConfig",
    "AdpTrainingFinishedEvent",
    "AdpTrainingSession",
    "CSV_FIELDS",
]
