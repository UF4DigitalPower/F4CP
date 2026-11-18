"""CH32V208 BLE transport. No Qt dependency; OTA is independently testable."""
import asyncio
import logging
import struct
import sys
import time

from bleak.exc import BleakGATTProtocolError
from .ota_package import TARGET, read_package, read_version
from .usb_diagnostics import format_usb_diagnostics
from .transfer_diagnostics import TransferDiagnostics

SERVICE = "9e9a0010-5213-4592-8f04-554634504857"
OTA = "9e9a0011-5213-4592-8f04-554634504857"
VERSION = "9e9a0012-5213-4592-8f04-554634504857"
COMM = "9e9a0021-5213-4592-8f04-554634504857"
NAME = "UF4Digitalpower V3"
IDLE, ERASING, RECEIVING, CHECKING, READY, ERROR, COMMITTED = range(7)
LOGGER = logging.getLogger("F4CP.BLE")


class UploadCancelled(Exception):
    pass


class InstallationUnconfirmed(Exception):
    pass


def create_ble_client(address, **kwargs):
    from bleak import BleakClient
    if sys.platform == "win32":
        from .windows_pairing import Uf4WinRTClient
        kwargs["backend"] = Uf4WinRTClient
    return BleakClient(address, **kwargs)


def decode_version(raw):
    if len(raw) != 20:
        raise ValueError("设备版本数据长度错误")
    protocol, major, minor, patch, build, target, layout, reserved = struct.unpack("<4B4I", raw)
    if (protocol, target, layout, reserved) != (1, TARGET, 1, 0):
        raise ValueError("连接设备并非兼容的 CH32V208 固件")
    return major, minor, patch, build


def version_text(version):
    return f"v{version[0]}.{version[1]}.{version[2]} · {version[3]}"


def decode_device_info(raw):
    if len(raw) != 20:
        raise ValueError("设备信息长度错误")
    protocol, available, reserved, jedec, capacity, user_base, target = struct.unpack("<BBH4I", raw)
    if (protocol != 1 or available not in (0, 1) or reserved or target != TARGET
            or capacity != 0x02000000 or user_base != 0x00100000):
        raise ValueError("设备存储信息不兼容")
    ready = bool(available and jedec in (0xEF4019, 0xEF6019, 0xEF7019))
    return ready, jedec, capacity, user_base


FLASH_UNAVAILABLE = (
    "W25Q256 未识别，无法 OTA。请核对 PB3=CLK、PB4=MISO、PB5=MOSI、PD2=/CS，"
    "并通过有线方式烧录本次 factory.hex 更新 Boot 和应用。"
)

AUTHENTICATION_FAILED = (
    "蓝牙认证未完成。请在系统配对提示中输入 005213；"
    "若已配对或刷机后仍失败，请点击“重新配对”清除该设备的电脑端旧绑定后重试。"
)


class BleDevice:
    def __init__(self, client_factory=None, changed=None, message=None):
        self.client_factory = client_factory
        self.changed = changed or (lambda connected: None)
        self.message = message or (lambda text: None)
        self.client = None
        self.address = ""
        self.version = None

    @property
    def connected(self):
        return self.client is not None and self.client.is_connected

    async def connect(self, address, pair=True, *, authentication_timeout=25):
        await self.disconnect()
        if self.client_factory is None:
            self.client_factory = create_ble_client
        self.address = address
        self.client = self.client_factory(address, timeout=60, pair=pair,
                                          winrt={"use_cached_services": False},
                                          disconnected_callback=lambda _: self.changed(False))
        stage = "Windows 建链、口令配对及服务发现"
        try:
            LOGGER.info("BLE connect: %s, pair=%s", address, pair)
            await self.client.connect()
            if not self.client.services.get_service(SERVICE):
                raise ValueError("未发现 OTA 服务，请先烧录 factory.hex")
            # OS pairing can finish before the peripheral's authenticated link
            # is ready. Retry only these read-only probes, never OTA writes.
            deadline = time.monotonic() + authentication_timeout
            notified = False
            while True:
                self.require_connection()
                try:
                    stage = "读取受保护的运行固件版本"
                    version = decode_version(bytes(await self.client.read_gatt_char(VERSION)))
                    stage = "读取受保护的 OTA 状态"
                    await self.status()
                    break
                except BleakGATTProtocolError as exc:
                    if exc.args[0] not in (0x05, 0x0F):
                        raise
                    if not notified:
                        self.message("正在等待设备完成认证和链路加密，请留意系统配对提示（005213）…")
                        notified = True
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise RuntimeError(AUTHENTICATION_FAILED) from exc
                    await asyncio.sleep(min(0.3, remaining))
            self.version = version
        except BaseException as exc:
            if not isinstance(exc, asyncio.CancelledError):
                LOGGER.exception("BLE 连接失败阶段：%s", stage)
                if isinstance(exc, OSError):
                    self.message(f"BLE 连接失败阶段：{stage}；详细调用位置已写入日志")
                    if (stage == "Windows 建链、口令配对及服务发现"
                            and getattr(exc, "winerror", None) == -2147024874):
                        self.message("Windows 服务发现错误 0x80070016：若刚升级设备固件，"
                                     "旧 GATT 属性缓存可能未刷新。可点击“重新配对”刷新所选设备的电脑端绑定。")
            try:
                await self.disconnect()
            except Exception:
                # Preserve the original failure, rather than replacing it with
                # a secondary Windows error while releasing the failed session.
                LOGGER.exception("BLE 连接失败后的资源释放也发生错误")
            raise
        self.changed(True)
        return self.version

    async def repair_pairing(self, address):
        """User-selected recovery; remove only this computer's selected bond."""
        await self.disconnect()
        if self.client_factory is None:
            self.client_factory = create_ble_client
        client = self.client_factory(address, timeout=60)
        self.message("正在清除所选设备在电脑上的旧绑定…")
        await client.unpair()
        self.message("旧绑定已清除，正在重新连接和配对（005213）…")
        return await self.connect(address)

    async def disconnect(self):
        client, self.client = self.client, None
        self.version = None
        try:
            if client is not None:
                await client.disconnect()
        finally:
            self.changed(False)

    def require_connection(self):
        if not self.connected:
            raise RuntimeError("请先连接设备")

    async def status(self):
        self.require_connection()
        raw = bytes(await self.client.read_gatt_char(OTA))
        if len(raw) != 20 or raw[0] != 1:
            raise ValueError("设备返回了无效的 OTA 状态")
        _, state, error, reserved, offset, size, checksum, capacity = struct.unpack("<4B4I", raw)
        if state not in range(7) or reserved:
            raise ValueError("设备 OTA 状态不受支持")
        if state == ERROR or error:
            details = {1: "命令无效", 2: "状态不允许", 3: "固件长度无效", 4: "接收偏移错误",
                       5: "W25Q256 擦除、写入或读取失败，请检查存储连接及供电", 6: "固件 CRC 校验失败"}
            raise RuntimeError(f"设备 OTA 错误 {error}：{details.get(error, '未知错误')}")
        return state, offset, size, checksum, capacity

    async def exchange(self, payload):
        self.require_connection()
        if not 1 <= len(payload) <= 20:
            raise ValueError("通信命令长度须为 1～20 字节")
        await self.client.write_gatt_char(COMM, payload, response=True)
        return bytes(await self.client.read_gatt_char(COMM))

    async def capabilities(self, fast):
        await self.client.write_gatt_char(OTA, bytes([8 if fast else 7]), response=True)
        raw = bytes(await self.client.read_gatt_char(OTA))
        if len(raw) != 20:
            raise ValueError("设备能力响应长度错误")
        magic, chunk, window, target, layout = struct.unpack("<4s4I", raw)
        if (target != TARGET or layout != 1 or not 4 <= chunk <= 236 or chunk % 4
                or magic != (b"UF4F" if fast else b"UF4C")
                or not 1 <= window <= (4 if fast else 1)):
            raise ValueError("设备 OTA 能力与升级包不兼容")
        return chunk, window

    async def usb_diagnostics(self):
        self.require_connection()
        if self.version is None or self.version[:3] < (0, 1, 2):
            raise RuntimeError("当前固件不支持 BLE USB 诊断，请先升级到 0.1.2")
        if self.version[:3] >= (0, 4, 0):
            raise RuntimeError("0.4.0 使用官方 USBFS 复合驱动，不支持旧版 USB 诊断分页")
        pages = []
        count = 9 if self.version[:3] >= (0, 1, 4) else (6 if self.version[:3] >= (0, 1, 3) else 3)
        for page in range(count):
            pages.append(await self.exchange(bytes([2, page])))
        return format_usb_diagnostics(pages)

    def transfer_chunk(self, advertised, fast):
        # MTU and WNR limits can change after the peripheral's MTU exchange.
        limit = min(244, max(23, self.client.mtu_size) - 3)
        if fast:
            characteristic = self.client.services.get_characteristic(OTA)
            limit = min(limit, characteristic.max_write_without_response_size)
        chunk = min(advertised, ((limit - 5) // 4) * 4)
        if chunk < 4:
            raise ValueError("蓝牙适配器的数据包长度不足")
        return chunk

    async def upload(self, package, cancelled, progress, phase, *, verify_timeout=90):
        image, checksum = read_package(package)
        expected_version = read_version(image)
        self.require_connection()
        info = decode_device_info(await self.exchange(b"\x00"))
        if not info[0]:
            raise RuntimeError(FLASH_UNAVAILABLE)
        initial = await self.status()
        if initial[0] != IDLE:
            raise RuntimeError("设备有未结束的 OTA 会话，请断开后重新连接")
        if len(image) > initial[4]:
            raise ValueError("升级包超过设备可用空间")
        committed = False
        started = False
        diagnostics = None

        def check_cancel():
            if cancelled():
                raise UploadCancelled("已取消升级")

        async def wait_state(wanted):
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                check_cancel()
                current = await self.status()
                if current[0] == wanted:
                    return current
                if current[0] not in (ERASING, CHECKING):
                    raise RuntimeError(f"升级状态异常：{current[0]}")
                await asyncio.sleep(0.05)
            raise TimeoutError("设备擦除或校验超时")

        try:
            check_cancel()
            characteristic = self.client.services.get_characteristic(OTA)
            fast = characteristic is not None and "write-without-response" in characteristic.properties
            if fast:
                try:
                    advertised, window = await self.capabilities(True)
                except Exception as exc:
                    # Only an explicit unsupported-command response permits
                    # fallback. Corrupt identities and link errors must surface.
                    if not isinstance(exc, BleakGATTProtocolError) or exc.args[0] not in (0x06, 0x13):
                        raise
                    fast = False
            if not fast:
                advertised, window = await self.capabilities(False)
            phase("正在准备 W25Q256 备用区", True)
            # Set before awaiting: a lost ATT response may still have started OTA.
            started = True
            await self.client.write_gatt_char(OTA, bytes([9 if fast else 1]) + struct.pack("<II", len(image), checksum), response=True)
            await wait_state(RECEIVING)
            # Erasing gives the controller time to negotiate. Refresh the device
            # capability snapshot and the OS's actual write limit before DATA.
            for attempt in range(11):
                check_cancel()
                advertised, window = await self.capabilities(fast)
                chunk = self.transfer_chunk(advertised, fast)
                if chunk > 12 or attempt == 10:
                    break
                await asyncio.sleep(0.15)
            mode = f"连续发送 · {window} 包/组" if fast else "逐包确认"
            phase(f"正在上传 · {mode} · {chunk} 字节/包", True)
            diagnostics = TransferDiagnostics(
                "V208 OTA", self.message, version=self.version, mtu=self.client.mtu_size,
                write_limit=characteristic.max_write_without_response_size if fast else None,
                chunk=chunk, window=window, streaming=fast)
            begun = time.monotonic()
            done = retries = 0
            while done < len(image):
                check_cancel()
                boundaries = [done]
                for _ in range(window):
                    check_cancel()
                    offset = boundaries[-1]
                    payload = image[offset:offset + chunk]
                    with diagnostics.measure("write", payload_size=len(payload)):
                        await self.client.write_gatt_char(OTA, b"\x02" + struct.pack("<I", offset) + payload, response=not fast)
                    boundaries.append(offset + len(payload))
                    await asyncio.sleep(0)
                    if boundaries[-1] == len(image):
                        break
                # ATT read follows the queued DATA on the same bearer. Only
                # the device's persisted, read-back-verified offset is progress.
                with diagnostics.measure("read"):
                    current = await self.status()
                confirmed = current[1]
                if (current[0] != RECEIVING or current[2:4] != (len(image), checksum)
                        or confirmed not in boundaries or (not fast and confirmed != boundaries[-1])):
                    raise RuntimeError("设备接收偏移或镜像身份不一致")
                retries = retries + 1 if confirmed != boundaries[-1] else 0
                if retries > 3:
                    raise RuntimeError("设备接收偏移连续重传失败，请重新连接后升级")
                done = confirmed
                diagnostics.confirm(done, boundaries[-1])
                elapsed = max(0.001, time.monotonic() - begun)
                speed = done / elapsed
                progress(done, len(image), speed, (len(image) - done) / speed if speed else 0)
            diagnostics.finish("传输结束（待 CRC 与安装确认）")
            phase("正在校验完整固件 CRC32", True)
            await self.client.write_gatt_char(OTA, b"\x03", response=True)
            ready = await wait_state(READY)
            if ready[1:4] != (len(image), len(image), checksum):
                raise RuntimeError("设备校验了不同的固件")
            check_cancel()
            phase("正在安装，等待设备重启和重连确认", False)
            committed = True
            try:
                await self.client.write_gatt_char(OTA, b"\x05", response=True)
            except Exception:
                # Reset may race with ATT response; only reconnection proves success.
                pass
            await self.disconnect()
            await asyncio.sleep(3)
            deadline = time.monotonic() + verify_timeout
            last_error = "尚未发现设备"
            while time.monotonic() < deadline:
                try:
                    await self.connect(self.address, pair=False)
                    current = await self.status()
                    if current[0] == IDLE and current[2:4] == (len(image), checksum) and (
                            expected_version is None or self.version == expected_version):
                        phase("升级完成，已确认运行版本与 CRC32", False)
                        return self.version
                    last_error = "运行版本或 CRC32 尚未匹配"
                except Exception as exc:
                    last_error = str(exc)
                await self.disconnect()
                await asyncio.sleep(2)
            raise InstallationUnconfirmed(f"已尝试提交，但未确认安装结果：{last_error}。可重新连接核对版本，必要时重新上电。")
        finally:
            if diagnostics is not None:
                diagnostics.finish("传输中断")
            if started and not committed and self.connected:
                try:
                    await self.client.write_gatt_char(OTA, b"\x04", response=True)
                except Exception:
                    # A disconnect also abandons an uncommitted firmware session.
                    await self.disconnect()
