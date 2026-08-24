import tempfile
import time
import unittest
from pathlib import Path

from PyQt5.QtCore import QCoreApplication, QObject, QEvent

from app.protocol.uf4com import (
    Uf4Command,
    Uf4FrameParser,
    build_frame,
    encode_tv,
)
from app.session.page_adp_training import (
    AdpCaptureConfig,
    AdpCaptureSavedEvent,
    AdpRequestAction,
    AdpRequestEvent,
    AdpStateEvent,
    AdpTrainingSession,
)
import app.session.page_adp_training.session_adp_training as session_module


class _FakeSerial:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.rx = bytearray()
        self.writes = []
        self.closed = False
        self._parser = Uf4FrameParser()
        type(self).instances.append(self)

    @property
    def in_waiting(self):
        return len(self.rx)

    def reset_input_buffer(self):
        self.rx.clear()

    def read(self, size):
        data = bytes(self.rx[:size])
        del self.rx[:size]
        return data

    def write(self, data):
        raw = bytes(data)
        self.writes.append(raw)
        for frame in self._parser.feed(raw):
            if int(frame.cmd) == int(Uf4Command.STREAM_START_REQ):
                payload = b"".join(
                    encode_tv(item, value)
                    for item, value in (
                        (0x11, 12000),
                        (0x0A, 24000),
                        (0x0C, 11000),
                        (0x0B, 1000),
                        (0x0D, 900),
                        (0x2A, 2000),
                        (0x2D, 300),
                    )
                )
                self.rx.extend(
                    build_frame(Uf4Command.STREAM_DATA, 0, payload)
                )
        return len(raw)

    def close(self):
        self.closed = True


class _EventReceiver(QObject):
    def __init__(self):
        super().__init__()
        self.events = []

    def event(self, event):
        self.events.append(event)
        return super().event(event)


class AdpTrainingSessionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QCoreApplication.instance() or QCoreApplication([])

    def pump_until(self, predicate, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.qt_app.processEvents()
            if predicate():
                return True
            time.sleep(0.005)
        self.qt_app.processEvents()
        return bool(predicate())

    def test_capture_request_reads_stream_and_saves_csv(self):
        original_serial = session_module.serial.Serial
        session_module.serial.Serial = _FakeSerial
        _FakeSerial.instances.clear()
        session = None
        try:
            with tempfile.TemporaryDirectory() as directory:
                dataset = Path(directory) / "capture.csv"
                receiver = _EventReceiver()
                session = AdpTrainingSession(receiver)
                config = AdpCaptureConfig("FAKE1", 921600, dataset)

                QCoreApplication.postEvent(
                    session,
                    AdpRequestEvent(
                        AdpRequestAction.START_CAPTURE,
                        config,
                    ),
                )
                self.assertTrue(
                    self.pump_until(
                        lambda: any(
                            isinstance(event, AdpStateEvent)
                            and event.payload.state == "capturing"
                            for event in receiver.events
                        )
                    )
                )

                QCoreApplication.postEvent(
                    session,
                    AdpRequestEvent(AdpRequestAction.STOP_CAPTURE),
                )
                self.assertTrue(
                    self.pump_until(
                        lambda: dataset.exists()
                        and any(
                            isinstance(event, AdpCaptureSavedEvent)
                            for event in receiver.events
                        )
                    )
                )

                rows = dataset.read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(rows), 2)
                self.assertIn("12.0", rows[1])
                self.assertTrue(_FakeSerial.instances[0].closed)
        finally:
            if session is not None:
                session.shutdown()
            session_module.serial.Serial = original_serial


if __name__ == "__main__":
    unittest.main()
