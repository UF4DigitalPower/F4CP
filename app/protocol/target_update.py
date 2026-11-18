"""G474 Link V3 staging and SWD programming over an authenticated BLE client."""
import asyncio
import struct
import time

from .ble_device import FLASH_UNAVAILABLE, UploadCancelled, decode_device_info
from .ota_package import crc

UPDATE = "9e9a0031-5213-4592-8f04-554634504857"
LIMIT = 128 * 1024
STATES = ("空闲", "擦除暂存区", "上传至暂存区", "暂存 CRC 校验", "待烧录", "连接 SWD",
          "擦除 G474", "写入 G474", "读回校验", "完成", "失败", "取消中")
ERRORS = ("无", "协议", "状态", "长度", "偏移", "W25Q256", "CRC", "SWD 忙", "SWD 通信",
          "芯片型号/容量", "读写保护或 Bank 交换", "目标 Flash", "超时", "向量表", "已取消")


def prepare_image(original):
    if not 8 <= len(original) <= LIMIT:
        raise ValueError("G474 固件须为 8 B～128 KiB 的原始 BIN")
    image = original + b"\xff" * (-len(original) % 8)
    sp, pc = struct.unpack_from("<II", image)
    if (sp % 8 or not 0x20000000 < sp <= 0x20020000 or not pc & 1
            or not 0x08000000 <= (pc & ~1) < 0x08000000 + len(image)):
        raise ValueError("G474 向量表无效；固件必须从 0x08000000 链接")
    return image


async def status(client, *, allow_terminal_error=False):
    raw = bytes(await client.read_gatt_char(UPDATE))
    if len(raw) != 20:
        raise ValueError("G474 状态长度错误")
    protocol, state, error, reserved, offset, size, checksum, limit = struct.unpack("<4B4I", raw)
    if protocol != 1 or reserved or state >= len(STATES) or limit != LIMIT or offset > size or size > limit:
        raise ValueError("G474 服务协议、容量或偏移不兼容")
    if (error or state == 10) and not (allow_terminal_error and state == 10 and error < len(ERRORS)):
        raise RuntimeError("G474 操作失败：" + (ERRORS[error] if error < len(ERRORS) else str(error)))
    return state, offset, size, checksum, limit


async def upload(device, original, cancelled, progress, phase):
    image = prepare_image(original)
    checksum = crc(image)
    device.require_connection()
    client = device.client
    if not client.services.get_characteristic(UPDATE):
        raise ValueError("当前设备不支持 G474 无线下载，请安装支持此功能的 Link V3 固件")
    if not decode_device_info(await device.exchange(b"\x00"))[0]:
        raise RuntimeError(FLASH_UNAVAILABLE)
    # BEGIN explicitly resets a finished/error session. Do not let a previous
    # cancellation permanently prevent the user from starting a new download.
    current = await status(client, allow_terminal_error=True)
    if current[0] not in (0, 9, 10):
        raise RuntimeError("G474 服务有未结束会话，请先断开并重新连接")
    # The on-board SWD programmer shares NOR with self OTA.
    if (await device.status())[0] != 0:
        raise RuntimeError("V208 有未结束的 OTA 会话，请先断开并重新连接")
    started = completed = programming = False
    started_at = time.monotonic()
    last_phase = None

    def check_cancel():
        if not programming and cancelled():
            raise UploadCancelled("G474 下载已取消")

    async def wait_state(wanted, allowed, timeout):
        nonlocal last_phase
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            check_cancel()
            current = await status(client)
            if current[2:4] != (len(image), checksum):
                raise RuntimeError("G474 镜像长度或 CRC 身份发生变化")
            if current[0] != last_phase:
                phase(STATES[current[0]], not programming)
                last_phase = current[0]
            if current[0] == wanted:
                return current
            if current[0] not in allowed:
                raise RuntimeError("G474 状态异常：" + STATES[current[0]])
            await asyncio.sleep(0.05)
        raise TimeoutError("G474 操作超时，未确认烧录成功")

    try:
        check_cancel()
        phase("正在准备 G474 暂存区", True)
        started = True  # A lost ATT response may still mean the command was accepted.
        await client.write_gatt_char(UPDATE, b"\x01" + struct.pack("<II", len(image), checksum), response=True)
        await wait_state(2, (1,), 120)
        chunk = min(239, max(23, client.mtu_size) - 8)
        for offset in range(0, len(image), chunk):
            check_cancel()
            data = image[offset:offset + chunk]
            await client.write_gatt_char(UPDATE, b"\x02" + struct.pack("<I", offset) + data, response=True)
            confirmed = await status(client)
            done = offset + len(data)
            if confirmed[:4] != (2, done, len(image), checksum):
                raise RuntimeError("G474 暂存偏移或镜像校验值不匹配")
            speed = done / max(0.001, time.monotonic() - started_at)
            progress(done, len(image), speed, (len(image) - done) / speed)
        check_cancel()
        await client.write_gatt_char(UPDATE, b"\x03", response=True)
        await wait_state(4, (3,), 120)
        check_cancel()
        programming = True
        phase("正在通过 SWD 烧录 G474，请勿断电或断开连接", False)
        await client.write_gatt_char(UPDATE, b"\x04", response=True)
        result = await wait_state(9, (5, 6, 7, 8), 600)
        if result[1:4] != (len(image), len(image), checksum):
            raise RuntimeError("G474 完成状态的长度或 CRC 不匹配")
        completed = True
    finally:
        if started and not completed and client.is_connected:
            try:
                await client.write_gatt_char(UPDATE, b"\x05", response=True)
            except Exception:
                pass
