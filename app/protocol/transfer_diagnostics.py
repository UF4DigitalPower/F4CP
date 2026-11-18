"""Passive timings for ordered BLE uploads; no extra GATT operations."""
from contextlib import contextmanager
import logging
import time

LOGGER = logging.getLogger("F4CP.BLETransfer")


class TransferDiagnostics:
    def __init__(self, target, message, *, version, mtu, write_limit, chunk,
                 window, streaming, clock=None):
        self.clock = clock or time.monotonic
        self.message = message
        self.target = target
        self.started = self.last_report = self.clock()
        self.closed = False
        self.confirmed = self.attempted = self.groups = 0
        self.partial_groups = 0
        # count, cumulative seconds, maximum seconds
        self.timings = {"write": [0, 0.0, 0.0], "read": [0, 0.0, 0.0]}
        running = (f"v{version[0]}.{version[1]}.{version[2]} / build {version[3]}"
                   if version else "未知")
        self._emit(f"BLE 上传诊断 [{target}] · 运行固件 {running} · MTU={mtu} · "
                   f"WNR上限={write_limit if streaming else '不适用'} B · "
                   f"{chunk} 字节/包 · {window} 包/组 · "
                   f"{'Write Command' if streaming else 'Write Request'}")

    def _emit(self, text):
        LOGGER.info(text)
        self.message(text)

    @contextmanager
    def measure(self, kind, *, payload_size=0):
        started = self.clock()
        if kind == "write":
            self.attempted += payload_size
        try:
            yield
        finally:
            elapsed = max(0.0, self.clock() - started)
            values = self.timings[kind]
            values[0] += 1
            values[1] += elapsed
            values[2] = max(values[2], elapsed)

    def confirm(self, offset, sent_end):
        self.confirmed = offset
        self.groups += 1
        self.partial_groups += offset != sent_end
        if self.clock() - self.last_report >= 5:
            self.report("进行中")

    def report(self, outcome):
        now = self.clock()
        elapsed = max(0.001, now - self.started)
        writes, reads = self.timings["write"], self.timings["read"]
        other = max(0.0, elapsed - writes[1] - reads[1])

        def timing(label, values):
            count, seconds, maximum = values
            return (f"{label} {count}次/{seconds:.3f}s "
                    f"均值{seconds * 1000 / max(1, count):.1f}ms "
                    f"最大{maximum * 1000:.1f}ms")

        self._emit(f"BLE 上传耗时 [{self.target}] {outcome} · "
                   f"确认 {self.confirmed} B / 尝试发送 {self.attempted} B · "
                   f"{self.confirmed / elapsed / 1024:.2f} KiB/s · 总计 {elapsed:.3f}s · "
                   f"{timing('写调用', writes)} · {timing('状态读取', reads)} · "
                   f"其他 {other:.3f}s · {self.groups}组/未完整确认{self.partial_groups}组")
        self.last_report = now

    def finish(self, outcome):
        if not self.closed:
            self.closed = True
            self.report(outcome)
