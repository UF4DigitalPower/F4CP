"""CMSIS-DAP discovery and G474 programming, using pyOCD directly in a worker."""
from dataclasses import dataclass
import io
import logging
import os
from pathlib import Path
import threading

from PyQt5.QtCore import QThread, pyqtSignal

from app.protocol.firmware_download import hex_segments

UF4_USB_ID = (0x1A86, 0xFE0C)
TARGET = "stm32g474rbtx"


def configure_usb():
    # UF4 uses its own product name, without the CMSIS-DAP substring. Register
    # only its explicit VID/PID, retaining HID usage filtering for composites.
    from pyocd.probe.pydapaccess.interface import common
    for table in (common.KNOWN_CMSIS_DAP_IDS, common.CMSIS_DAP_IDS_TO_FILTER_BY_USAGE_PAGE):
        if UF4_USB_ID not in table:
            table.append(UF4_USB_ID)


def connected_probes():
    configure_usb()
    from pyocd.core.session import Session
    from pyocd.probe.cmsis_dap_probe import CMSISDAPProbe
    # Discovery also consults Session.get_current(). Keep an explicit options
    # session alive so discovery never loads a working-directory pyocd.yaml.
    discovery = Session(None, options={"no_config": True, "project_dir": os.getcwd(),
                                       "cmsis_dap.prefer_v1": True})
    return list(CMSISDAPProbe.get_all_connected_probes())


def select_probe(uid):
    if not uid:
        raise ValueError("请先扫描并选择 DAPLink 探针")
    matches = [probe for probe in connected_probes() if probe.unique_id == uid]
    if len(matches) != 1:
        raise ValueError("所选 DAPLink 已断开或 UID 不唯一，请重新扫描")
    return matches[0]


def session_options(pack, frequency, connect_mode):
    if not Path(pack).is_file():
        raise ValueError("缺少本地 STM32G4 Pack，请重新安装完整 F4CP 目录")
    if not 10000 <= frequency <= 4000000 or connect_mode not in ("under-reset", "halt", "pre-reset", "attach"):
        raise ValueError("SWD 频率或连接模式无效")
    return {"target_override": TARGET, "pack": str(Path(pack).resolve()),
            "frequency": frequency, "connect_mode": connect_mode, "auto_unlock": False,
            "pack.debug_sequences.disabled_sequences": ["DebugDeviceUnlock"],
            # This Pack's DebugPortStop can unlock option bytes and launch an
            # option reload. Programming application flash must not do either.
            "pack.debug_sequences.debugvars": "DoOptionByteLoading=0;",
            "resume_on_disconnect": False, "no_config": True, "cmsis_dap.prefer_v1": True,
            "hide_programming_progress": True, "user_script": os.devnull, "project_dir": os.getcwd()}


def check_target(target, segments=None):
    device_id = target.read32(0xE0042000) & 0xFFF
    capacity = target.read16(0x1FFF75E0)
    if device_id != 0x469 or capacity != 128:
        raise ValueError(f"目标型号/容量不匹配：DEV_ID=0x{device_id:03X}，Flash={capacity} KiB")
    # Match the on-board programmer's refusal to alter protected targets.
    optr = target.read32(0x40022020)
    if optr & 0xFF != 0xAA or optr & (1 << 20) or target.read32(0x40010000) & 0x100:
        raise ValueError("目标存在读保护或 Bank 交换，拒绝自动解除保护")
    if optr & 0x400000 and segments is not None:
        if any(address < 0x08000000 or address + len(data) > 0x08010000
               for address, data in segments):
            raise ValueError("Flash 布局：当前 128 KiB G474 为双 Bank 模式，连续 BIN/HEX "
                             "不能跨越 0x08010000；Bank 2 从 0x08040000 开始。未擦写，不自动修改 DBANK。")
    # Same protection registers/masks as OTA/target_update.c, for active banks.
    for bank in range(2 if optr & 0x400000 else 1):
        base = 0x40022000 + bank * 0x20
        if ((target.read32(base + 0x24) & 0x7FFF) <= (target.read32(base + 0x28) & 0x7FFF)
                or target.read32(0x40022070 + bank * 4) & 255):
            raise ValueError("目标存在 PCROP 或安全区保护，拒绝修改选项字节")
        for area in range(2):
            value = target.read32(base + 0x2C + area * 4)
            if (value & 0x7F) <= ((value >> 16) & 0x7F):
                raise ValueError("目标存在写保护，拒绝修改选项字节")
    layout = "双 Bank，起始连续区 64 KiB" if optr & 0x400000 else "单 Bank，连续 128 KiB"
    return f"{TARGET.upper()} · DEV_ID 0x{device_id:03X} · Flash {capacity} KiB · {layout}"


def image_segments(firmware):
    if firmware.suffix == ".bin":
        return [(0x08000000, firmware.data)]
    memory = hex_segments(firmware.data)
    segments = []
    for address in sorted(memory):
        if not segments or address != segments[-1][0] + len(segments[-1][1]):
            segments.append((address, bytearray()))
        segments[-1][1].append(memory[address])
    return segments


def program_g474(session, firmware, progress, message):
    from pyocd.flash.file_programmer import FileProgrammer
    target = session.target
    segments = image_segments(firmware)
    message(check_target(target, segments))
    source = io.BytesIO(firmware.data) if firmware.suffix == ".bin" else io.StringIO(firmware.data.decode("ascii"))
    message("pyOCD 正在擦除和写入 G474…")
    FileProgrammer(session, progress=lambda value: progress(min(85, int(value * 85))),
                   chip_erase="sector", smart_flash=True, trust_crc=False, keep_unwritten=True).program(
                       source, file_format=firmware.suffix[1:], base_address=0x08000000)
    target.halt()
    message("正在读回完整固件并逐字节校验…")
    total = sum(len(data) for _, data in segments)
    done = 0
    for address, data in segments:
        for offset in range(0, len(data), 1024):
            expected = bytes(data[offset:offset + 1024])
            actual = bytes(target.read_memory_block8(address + offset, len(expected)))
            if actual != expected:
                raise RuntimeError(f"G474 读回校验失败：0x{address + offset:08X}，保持目标暂停")
            done += len(expected)
            progress(85 + done * 14 // total)
    target.reset()
    message("pyOCD 写入与完整读回校验通过，目标已复位运行")


@dataclass(frozen=True)
class ProbeInfo:
    uid: str
    description: str


class _WorkerLog(logging.Handler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.thread_id = threading.get_ident()

    def emit(self, record):
        if record.thread == self.thread_id:
            self.callback(record.getMessage())


class PyOcdWorker(QThread):
    probes = pyqtSignal(list)
    message = pyqtSignal(str)
    progress = pyqtSignal(int)
    result = pyqtSignal(bool, str)

    def __init__(self, action, *, uid="", pack="", frequency=100000, connect_mode="under-reset", firmware=None, parent=None):
        super().__init__(parent)
        self.action, self.uid, self.pack = action, uid, pack
        self.frequency, self.connect_mode, self.firmware = frequency, connect_mode, firmware

    def run(self):
        logger = logging.getLogger("pyocd")
        handler = _WorkerLog(self.message.emit)
        logger.addHandler(handler)
        try:
            if self.action == "scan":
                probes = [ProbeInfo(probe.unique_id, probe.description) for probe in connected_probes()]
                self.probes.emit(probes)
                self.result.emit(True, f"扫描完成，发现 {len(probes)} 个 CMSIS-DAP 探针")
                return
            if self.action not in ("connect", "program"):
                raise ValueError("未知 pyOCD 操作")
            from pyocd.core.session import Session
            options = session_options(self.pack, self.frequency, self.connect_mode)
            probe = select_probe(self.uid)
            self.message.emit(f"连接 DAPLink：{probe.description} · UID {probe.unique_id}")
            with Session(probe, options=options) as session:
                if self.action == "connect":
                    self.message.emit(check_target(session.target))
                else:
                    if self.firmware is None:
                        raise ValueError("尚未选择固件")
                    program_g474(session, self.firmware, self.progress.emit, self.message.emit)
            self.result.emit(True, "pyOCD 目标识别通过，会话已释放；目标可能保持暂停，下载或手动复位后运行" if self.action == "connect" else
                             "G474 下载完成，pyOCD 完整读回校验通过并复位运行")
        except Exception as exc:
            self.result.emit(False, str(exc))
        finally:
            logger.removeHandler(handler)
