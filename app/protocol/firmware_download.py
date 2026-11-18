"""File validation and OpenOCD invocation plans; never starts a hardware operation."""
from dataclasses import dataclass
from pathlib import Path
import shutil
import struct

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


def load_firmware(path, target, mode, base=0):
    path = Path(path)
    if target not in (V208, G474) or mode not in (WIRELESS, WIRED):
        raise ValueError("未知芯片或连接方式")
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("文件超过支持的固件大小")
    data, suffix = path.read_bytes(), path.suffix.lower()
    detail = ""
    if mode == WIRELESS and target == V208:
        if suffix != ".ota":
            raise ValueError("V208 无线升级仅接受 .ota 包")
        image, checksum = read_package(data)
        version = read_version(image)
        if version is None:
            raise ValueError("OTA 包缺少版本身份，无法在重连后确认安装")
        detail = f"v{version[0]}.{version[1]}.{version[2]} · build {version[3]} · "
    elif target == G474:
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
    else:
        if suffix == ".bin":
            if base not in (0, 0x4000) or not 256 <= len(data) <= 0x70000 - base:
                raise ValueError("V208 BIN 长度或起始地址无效")
            image = data
            start = base
        elif suffix == ".hex":
            memory = hex_segments(data)
            low, high = min(memory), max(memory)
            if low not in (0, 0x4000) or high >= 0x70000:
                raise ValueError("V208 HEX 地址须位于 0～0x6FFFF，起点为 0 或 0x4000")
            image = bytes(memory.get(i, 255) for i in range(low, high + 1))
            start = low
        else:
            raise ValueError("V208 有线下载支持 BIN / HEX；OTA 不能直接有线烧录")
        validate_v208_wired(image, start)
        checksum = crc(image)
    return Firmware(data, suffix, f"{path.name} · {detail}{len(image):,} B · CRC32 {checksum:08X}")


def validate_v208_wired(image, start):
    if len(image) < 256:
        raise ValueError("V208 固件过短")
    if image[0x14:0x18] == bytes.fromhex("a9bdf9f5"):
        return
    # The confirmed official 0.3.0 standalone image has no UF4 OTA marker.
    # Its reset vector is JAL x0 followed by the WCH absolute vector table.
    instruction = struct.unpack_from("<I", image)[0]
    offset = (((instruction >> 31) << 20) | (((instruction >> 21) & 0x3ff) << 1)
              | (((instruction >> 20) & 1) << 11) | (instruction & 0xff000))
    if offset & 0x100000:
        offset -= 0x200000
    vectors = struct.unpack_from("<II", image, 12)
    if (instruction & 0xfff != 0x06f or not 0 <= offset < len(image)
            or image[4:12] != bytes(8)
            or any(address % 2 or not start <= address < start + len(image) for address in vectors)):
        raise ValueError("未发现兼容的 CH32V208 RISC-V 启动入口，拒绝烧录")


def tcl_word(value):
    value = str(value).replace("\\", "/")
    if "\n" in value or "\r" in value:
        raise ValueError("路径不能包含换行符")
    for char in ('$', '[', ']', '"'):
        value = value.replace(char, "\\" + char)
    return '"' + value + '"'


def openocd_command(executable, target, firmware_path, base=0, config="", serial=""):
    executable = shutil.which(executable) or executable
    if not Path(executable).is_file():
        raise ValueError("请选择可用的 OpenOCD 程序")
    arguments = ["-c", "gdb_port disabled; tcl_port disabled; telnet_port disabled"]
    if target == V208:
        if not Path(config).is_file():
            raise ValueError("请选择 WCH OpenOCD 配套的 bin/wch-riscv.cfg")
        arguments += ["-f", str(Path(config).resolve())]
    elif target == G474:
        arguments += ["-f", "interface/cmsis-dap.cfg", "-c", "cmsis_dap_vid_pid 0x1a86 0xfe0c",
                      "-c", "transport select swd", "-f", "target/stm32g4x.cfg", "-c", "adapter speed 1000"]
    else:
        raise ValueError("未知目标芯片")
    if serial.strip():
        arguments += ["-c", "adapter serial " + tcl_word(serial.strip())]
    if target == G474:
        arguments += ["-c", 'init; reset halt; '
                      'if {([mrw 0xe0042000] & 0xfff) != 0x469 || [mrh 0x1fff75e0] != 128} '
                      '{error "Expected G474/G484 with 128 KiB Flash"}']
    address = ""
    if Path(firmware_path).suffix.lower() == ".bin":
        address = f" 0x{(0x08000000 if target == G474 else base):08x}"
    arguments += ["-c", f"program {tcl_word(firmware_path)} verify reset{address}; echo F4CP_VERIFY_OK; shutdown"]
    return str(Path(executable).resolve()), arguments
