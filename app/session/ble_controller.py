"""Keep WinRT BLE and its asyncio loop on one worker thread."""
import asyncio
import logging
import threading

from PyQt5.QtCore import QThread, pyqtSignal
from app.protocol.ble_device import BleDevice, NAME, SERVICE, UploadCancelled, version_text

LOGGER = logging.getLogger("F4CP.BLEController")


class BleController(QThread):
    ready = pyqtSignal()
    devices = pyqtSignal(list)
    connected = pyqtSignal(bool)
    version = pyqtSignal(str)
    message = pyqtSignal(str)
    progress = pyqtSignal(int, int, float, float)
    phase = pyqtSignal(str, bool)
    busy = pyqtSignal(bool)
    result = pyqtSignal(bool, str)
    received = pyqtSignal(bytes)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.loop = None
        self.device = None
        self._cancel = threading.Event()
        self._busy = False
        self._active = None
        self._closing = False

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.device = BleDevice(changed=self.connected.emit, message=self.message.emit)
        if self.isInterruptionRequested():
            self.loop.close()
            return
        self.loop.call_soon(self.ready.emit)
        try:
            self.loop.run_forever()
        finally:
            pending = asyncio.all_tasks(self.loop)
            for task in pending:
                task.cancel()
            self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self.loop.run_until_complete(self.device.disconnect())
            self.loop.close()

    def submit(self, action, *args):
        if self._busy or self._closing or self.loop is None or not self.loop.is_running():
            return False
        self._busy = True
        self._cancel.clear()
        self.busy.emit(True)

        async def work():
            try:
                await getattr(self, "_" + action)(*args)
            except UploadCancelled:
                self.result.emit(False, "下载已取消，未提交安装或目标烧录")
            except Exception as exc:
                LOGGER.exception("BLE 操作失败：%s", action)
                self.result.emit(False, str(exc))
            finally:
                self._busy = False
                self.busy.emit(False)

        self._active = asyncio.run_coroutine_threadsafe(work(), self.loop)
        return True

    async def _scan(self):
        from bleak import BleakScanner
        self.message.emit("正在扫描附近的 UF4 设备…")
        discovered = await BleakScanner.discover(timeout=6, return_adv=True)
        matches = []
        for device, adv in discovered.values():
            if NAME in (device.name, adv.local_name) or SERVICE in [s.lower() for s in adv.service_uuids]:
                matches.append((device.name or adv.local_name or "UF4", device.address, adv.rssi))
        self.devices.emit(matches)
        self.message.emit(f"找到 {len(matches)} 台设备")

    async def _connect(self, address):
        self.message.emit("正在连接，使用设备配对码 005213 进行认证，请留意系统提示…")
        version = await self.device.connect(address)
        self.version.emit(version_text(version))
        self.message.emit("已连接，身份校验通过")
        await self._exchange(b"\x00")

    async def _disconnect(self):
        await self.device.disconnect()
        self.version.emit("未连接")

    async def _repair_pairing(self, address):
        version = await self.device.repair_pairing(address)
        self.version.emit(version_text(version))
        self.message.emit("已重新配对，设备身份与安全链路校验通过")
        await self._exchange(b"\x00")

    async def _exchange(self, payload):
        raw = await self.device.exchange(payload)
        self.received.emit(raw)

    async def _usb_diagnostics(self):
        self.message.emit(await self.device.usb_diagnostics())

    async def _upload(self, package):
        version = await self.device.upload(package, self._cancel.is_set, self.progress.emit, self.phase.emit)
        self.version.emit(version_text(version))
        self.result.emit(True, "固件升级成功，重连后的版本、长度和 CRC32 已匹配")
        try:
            await self._exchange(b"\x00")
        except Exception as exc:
            self.message.emit(f"升级已确认，刷新存储信息失败：{exc}，可手动重新读取")

    async def _target_upload(self, image):
        from app.protocol.target_update import upload
        await upload(self.device, image, self._cancel.is_set, self.progress.emit, self.phase.emit)
        self.result.emit(True, "G474 烧录完成，设备已读回校验长度与 CRC32 并复位运行")

    def cancel(self):
        self._cancel.set()

    def shutdown(self):
        if not self.isRunning():
            return True
        self._closing = True
        self._cancel.set()
        if self._active and not self._active.done():
            self._active.cancel()
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self.loop.stop)
        else:
            self.requestInterruption()
        return self.wait(15000)
