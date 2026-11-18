"""CH32V208RBT6 UF4 Power OTA v1 package and initial UART factory image."""
import argparse
from pathlib import Path
import struct
import zlib

APP_BASE = 0x4000
SLOT_SIZE = 428 * 1024
ACTIVE_BASE = 0x6F000
INTERNAL_END = 0x70000
TARGET = 0x208B0001
MAGIC = b"UF4OTA1\0"
MANIFEST_MAGIC = 0x31484655


def crc(data):
    return zlib.crc32(data) & 0xFFFFFFFF


def validate_image(image):
    if not 256 <= len(image) <= SLOT_SIZE or len(image) % 4:
        raise ValueError("Application must be 256..438272 bytes, aligned to 4 bytes")
    if image[0x14:0x18] != bytes.fromhex("a9bdf9f5"):
        raise ValueError("Missing CH32V208 startup marker")


def make_package(image):
    validate_image(image)
    header = struct.pack("<8s5I", MAGIC, TARGET, APP_BASE, len(image), crc(image), 1)
    return header + struct.pack("<I", crc(header)) + image


def read_version(image):
    magic = b"UF4VER1\0"
    offset = image.find(magic)
    if offset < 0:
        return None
    if image.find(magic, offset + 1) >= 0 or offset + 28 > len(image):
        raise ValueError("Duplicate or truncated firmware version identity")
    protocol, major, minor, patch, build, target, layout, reserved = struct.unpack("<4B4I", image[offset + 8:offset + 28])
    if (protocol, target, layout, reserved) != (1, TARGET, 1, 0):
        raise ValueError("Incompatible firmware version identity")
    return major, minor, patch, build


def read_package(data):
    if len(data) < 32:
        raise ValueError("Truncated OTA header")
    magic, target, base, size, checksum, version, header_crc = struct.unpack("<8s6I", data[:32])
    if (magic, target, base, version) != (MAGIC, TARGET, APP_BASE, 1):
        raise ValueError("Not a compatible UF4 Power Hub CH32V208F OTA v1 package")
    if crc(data[:28]) != header_crc or len(data) != 32 + size:
        raise ValueError("Invalid OTA header or package length")
    image = data[32:]
    validate_image(image)
    if crc(image) != checksum:
        raise ValueError("OTA image CRC mismatch")
    read_version(image)
    return image, checksum


def manifest(image):
    header = struct.pack("<3I", MANIFEST_MAGIC, len(image), crc(image))
    return header + struct.pack("<I", crc(header))


def intel_hex(segments):
    lines = []
    last_upper = None

    def record(address, kind, payload):
        raw = bytes([len(payload)]) + address.to_bytes(2, "big") + bytes([kind]) + payload
        return ":" + (raw + bytes([-sum(raw) & 255])).hex().upper()

    for start, data in segments:
        for offset in range(0, len(data), 16):
            address = start + offset
            upper = address >> 16
            if upper != last_upper:
                lines.append(record(0, 4, upper.to_bytes(2, "big")))
                last_upper = upper
            lines.append(record(address & 0xFFFF, 0, data[offset:offset + 16]))
    lines.append(record(0, 1, b""))
    return "\n".join(lines) + "\n"


def build(boot, image, out):
    # Pad only at the end, so ROM writes and all CRCs use the same dword size.
    image += b"\xff" * (-len(image) % 4)
    validate_image(image)
    if not 24 <= len(boot) <= APP_BASE or boot[0x14:0x18] != bytes.fromhex("a9bdf9f5"):
        raise ValueError("Invalid bootloader or bootloader exceeds 16 KiB")
    out.mkdir(parents=True, exist_ok=True)
    (out / "UF4_CH32V208.ota").write_bytes(make_package(image))
    # Factory initializes internal program Flash only. External pending
    # metadata must be erased separately when recovering an interrupted install.
    factory = bytearray(b"\xff" * INTERNAL_END)
    factory[:len(boot)] = boot
    factory[APP_BASE:APP_BASE + len(image)] = image
    factory[ACTIVE_BASE:ACTIVE_BASE + 16] = manifest(image)
    (out / "UF4_CH32V208_factory.bin").write_bytes(factory)
    (out / "UF4_CH32V208_factory.hex").write_text(intel_hex([(0, factory)]), encoding="ascii")
    version = read_version(image)
    version_text = f"v{version[0]}.{version[1]}.{version[2]} build {version[3]}" if version else "legacy (no version)"
    print(f"OTA: {version_text}, {len(image)} bytes, CRC32 {crc(image):08X}; factory image at 0x00000000")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boot", required=True, type=Path)
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    build(args.boot.read_bytes(), args.app.read_bytes(), args.out)
