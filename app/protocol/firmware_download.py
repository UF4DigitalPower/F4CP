"""Validate V208 wireless OTA and G474 wired/wireless firmware files."""
from dataclasses import dataclass
from pathlib import Path

from .ota_package import crc, read_package, read_version
from .target_update import prepare_image

V208, G474 = "v208", "g474"
WIRELESS, WIRED = "wireless", "wired"


@dataclass(frozen=True)
class Firmware:
    data: bytes
    suffix: str
    summary: str


def hex_segments(data):
    """Read checked Intel HEX records, rejecting overlaps and non-Flash payloads later."""
    memory = {}
    upper = 0
    eof = False
    try:
        for line in data.decode("ascii").splitlines():
            if not line.strip():
                continue
            if eof or not line.startswith(":"):
                raise ValueError()
            record = bytes.fromhex(line[1:])
            if len(record) < 5 or len(record) != record[0] + 5 or sum(record) & 255:
                raise ValueError()
            size, kind = record[0], record[3]
            address = int.from_bytes(record[1:3], "big")
            payload = record[4:-1]
            if kind == 0:
                if address + size > 0x10000:
                    raise ValueError()
                for i, value in enumerate(payload):
                    location = upper + address + i
                    if location in memory:
                        raise ValueError()
                    memory[location] = value
            elif kind == 1 and size == 0 and address == 0:
                eof = True
            elif kind in (2, 4) and size == 2 and address == 0:
                upper = int.from_bytes(payload, "big") << (4 if kind == 2 else 16)
            elif kind in (3, 5) and size == 4 and address == 0:
                pass
            else:
                raise ValueError()
        if not eof or not memory:
            raise ValueError()
    except (ValueError, UnicodeError) as exc:
        raise ValueError("HEX 格式、校验和、结束记录或地址重叠无效") from exc
    return memory


def load_firmware(path, target, mode):
    path = Path(path)
    if target not in (V208, G474) or mode not in (WIRELESS, WIRED):
        raise ValueError("未知芯片或连接方式")
    if target == V208 and mode != WIRELESS:
        raise ValueError("V208 仅支持无线 OTA 升级")
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("文件超过支持的固件大小")
    data, suffix = path.read_bytes(), path.suffix.lower()
    detail = ""
    if target == V208:
        if suffix != ".ota":
            raise ValueError("V208 无线升级仅接受 .ota 包")
        image, checksum = read_package(data)
        version = read_version(image)
        if version is None:
            raise ValueError("OTA 包缺少版本身份，无法在重连后确认安装")
        detail = f"v{version[0]}.{version[1]}.{version[2]} · build {version[3]} · "
    else:
        if suffix == ".bin":
            image = prepare_image(data)
        elif suffix == ".hex" and mode == WIRED:
            memory = hex_segments(data)
            low, high = min(memory), max(memory)
            if low != 0x08000000 or high >= 0x08020000:
                raise ValueError("G474 HEX 必须位于 0x08000000～0x0801FFFF")
            image = prepare_image(bytes(memory.get(i, 255) for i in range(low, high + 1)))
        else:
            raise ValueError("G474 无线下载使用 BIN；有线下载支持 BIN / HEX")
        checksum = crc(image)
    return Firmware(data, suffix, f"{path.name} · {detail}{len(image):,} B · CRC32 {checksum:08X}")
