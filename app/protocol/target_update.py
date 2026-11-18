"""G474 Link V3 staging and SWD programming over an authenticated BLE client."""
import asyncio
import struct
import time
from bleak.exc import BleakGATTProtocolError

from .ble_device import FLASH_UNAVAILABLE, UploadCancelled, decode_device_info
from .ota_package import crc
from .transfer_diagnostics import TransferDiagnostics

UPDATE = "9e9a0031-5213-4592-8f04-554634504857"
LIMIT = 128 * 1024
# DATA Write Responses already acknowledge persisted/read-back-verified bytes.
# Read the full session identity once per bounded group, not once per packet.
ACK_WINDOW = 8
STREAM_WINDOW = 4
STATES = ("空闲", "擦除暂存区", "上传至暂存区", "暂存 CRC 校验", "待烧录", "连接 SWD",
          "擦除 G474", "写入 G474", "读回校验", "完成", "失败", "取消中")
ERRORS = ("无", "协议", "状态", "长度", "偏移", "W25Q256", "CRC", "SWD 忙", "SWD 通信",
          "芯片型号/容量", "读写保护或 Bank 交换", "目标 Flash", "超时", "向量表", "已取消",
          "Flash 布局：双 Bank 模式下连续 BIN 不能超过 64 KiB，不自动修改 DBANK")


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


async def capabilities(client):
    # Read-only query on the existing characteristic: no new GATT handles.
    await client.write_gatt_char(UPDATE, b"\x07", response=True)
    raw = bytes(await client.read_gatt_char(UPDATE))
    if len(raw) != 20:
        raise ValueError("G474 连续传输能力响应长度错误")
    magic, chunk, window, base, limit = struct.unpack("<4s4I", raw)
    if (magic != b"G4F1" or not 1 <= chunk <= 239 or not 1 <= window <= STREAM_WINDOW
            or base != 0x08000000 or limit != LIMIT):
        raise ValueError("G474 连续传输能力或目标不兼容")
    return chunk, window


def transfer_chunk(client, characteristic, advertised=239, *, streaming=False):
    limit = min(244, max(23, client.mtu_size) - 3)
    if streaming:
        limit = min(limit, characteristic.max_write_without_response_size)
    chunk = min(advertised, limit - 5)
    if chunk < 1:
        raise ValueError("蓝牙适配器的数据包长度不足")
    return chunk


async def upload(device, original, cancelled, progress, phase):
    image = prepare_image(original)
    checksum = crc(image)
    device.require_connection()
    client = device.client
    characteristic = client.services.get_characteristic(UPDATE)
    if not characteristic:
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
    last_phase = None
    diagnostics = None

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
        streaming = "write-without-response" in getattr(characteristic, "properties", ())
        advertised, window = 239, ACK_WINDOW
        if streaming:
            try:
                advertised, window = await capabilities(client)
            except BleakGATTProtocolError as exc:
                # Only explicit unsupported-command replies permit fallback.
                # Authentication/link errors and malformed identities surface.
                if exc.args[0] not in (0x06, 0x13):
                    raise
                streaming = False
        phase("正在准备 G474 暂存区", True)
        started = True  # A lost ATT response may still mean the command was accepted.
        await client.write_gatt_char(UPDATE, bytes([6 if streaming else 1]) + struct.pack("<II", len(image), checksum), response=True)
        await wait_state(2, (1,), 120)
        # Small images finish NOR erase before the peripheral's delayed MTU
        # exchange. Give it a bounded opportunity, retaining MTU 23 support.
        for attempt in range(11):
            check_cancel()
            if streaming:
                advertised, window = await capabilities(client)
            chunk = transfer_chunk(client, characteristic, advertised, streaming=streaming)
            if chunk > 15 or attempt == 10:
                break
            await asyncio.sleep(0.15)
        if not streaming:
            window = ACK_WINDOW
        mode = f"连续发送、{window} 包/组" if streaming else "逐包应答（连续传输需 V208 0.4.3）"
        phase(f"正在上传 G474 暂存区 · {chunk} 字节/包 · {mode}", True)
        diagnostics = TransferDiagnostics(
            "G474 暂存", device.message, version=device.version, mtu=client.mtu_size,
            write_limit=characteristic.max_write_without_response_size if streaming else None,
            chunk=chunk, window=window, streaming=streaming)
        started_at = time.monotonic()
        done = 0
        while done < len(image):
            check_cancel()
            # Writes remain ordered on one ATT bearer. A status read after each
            # bounded group confirms persisted bytes, including Write Commands.
            updated_chunk = transfer_chunk(client, characteristic, advertised, streaming=streaming)
            if updated_chunk != chunk:
                chunk = updated_chunk
                phase(f"正在上传 G474 暂存区 · {chunk} 字节/包 · {mode}", True)
            end = done
            for _ in range(window):
                check_cancel()
                data = image[end:end + chunk]
                with diagnostics.measure("write", payload_size=len(data)):
                    await client.write_gatt_char(UPDATE, b"\x02" + struct.pack("<I", end) + data, response=not streaming)
                end += len(data)
                if end == len(image):
                    break
            with diagnostics.measure("read"):
                confirmed = await status(client)
            if confirmed[:4] != (2, end, len(image), checksum):
                raise RuntimeError("G474 暂存偏移或镜像校验值不匹配")
            done = end
            diagnostics.confirm(done, end)
            speed = done / max(0.001, time.monotonic() - started_at)
            progress(done, len(image), speed, (len(image) - done) / speed)
        diagnostics.finish("传输结束（待 CRC 与 SWD 烧录确认）")
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
        if diagnostics is not None:
            diagnostics.finish("传输中断")
        if started and not completed and client.is_connected:
            try:
                await client.write_gatt_char(UPDATE, b"\x05", response=True)
            except Exception:
                pass
