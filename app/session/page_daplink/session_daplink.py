# -*- coding: utf-8 -*-
"""DAPLink 下载会话 — 基于 uf4-target + pyOCD 的真实实现。

设计：
- 页面通过 postEvent 发送 DaplinkRequestEvent（action: scan_probes / load_targets /
  connect / download），会话在 customEvent 中分派到后台 QThread 执行。
- 后台线程调用 DAPLINK\\tools\\uf4-target\\uf4-target.exe 切换 SWD 目标
  （G474 / F429 / ESP32），再用 pyOCD 完成 G474RBT6/F429IGT6 固件下载。
- 结果通过事件回传给页面（_event_receiver），页面 event() 处理并刷新 UI。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

from PyQt5.QtCore import QCoreApplication, QEvent, QObject, QThread, pyqtSignal

# ---------------------------------------------------------------------------
# 事件类型（页面 event() 用事件类的 EVENT_TYPE 判断）
# ---------------------------------------------------------------------------


class DaplinkProgrammerEventType(IntEnum):
    """兼容枚举，保留页面引用；实际事件类型以各事件类 EVENT_TYPE 为准。"""

    LOG = 1
    MESSAGE = 2
    STATE = 3
    PROBES = 4
    TARGETS = 5
    DEVICE_INFO = 6
    PROGRESS = 7
    ACTION_FINISHED = 8


def _new_event_type() -> int:
    return int(QEvent.registerEventType())


# ---------------------------------------------------------------------------
# 数据类（字段与 page_daplink.py 页面引用保持一致）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DaplinkProbeInfo:
    index: int = 0
    uid: str = ""
    description: str = ""
    product_name: str = ""
    vendor_name: str = ""


@dataclass(frozen=True)
class DaplinkTargetInfo:
    target_id: str = ""
    part_number: str = ""
    target_name: str = ""
    family: str = ""
    flash_start: str = "--"
    flash_size: str = "--"
    ram_size: str = "--"
    pack_name: str = ""
    pack_version: str = ""


@dataclass(frozen=True)
class DaplinkDeviceInfo:
    probe_uid: str = "--"
    probe_description: str = "--"
    vendor: str = "--"
    product: str = "--"
    target_name: str = "--"
    part_number: str = "--"
    family: str = "--"
    flash_start: str = "--"
    flash_size: str = "--"
    ram_size: str = "--"
    pack_name: str = "--"
    pack_version: str = "--"
    idcode: str = "--"


@dataclass(frozen=True)
class Esp32PortInfo:
    device: str = ""
    description: str = ""
    hwid: str = ""
    bus_reported_description: str = ""


@dataclass(frozen=True)
class DaplinkConnectConfig:
    probe_uid: str | None = None
    target_name: str = ""
    frequency: str = ""
    connect_mode: str = ""


@dataclass(frozen=True)
class DaplinkRequestPayload:
    action: str = ""
    connect: DaplinkConnectConfig | None = None
    file_path: str = ""
    base_address: str = ""
    erase_mode: str = ""
    smart_flash: bool = True
    trust_crc: bool = False
    reset_after_download: bool = True
    esp_port: str = ""
    esp_baud: str = ""
    esp_address: str = ""
    esp_flash_mode: str = ""
    esp_flash_freq: str = ""
    esp_flash_size: str = ""
    esp_erase: bool = False
    silent: bool = False


@dataclass(frozen=True)
class ActionFinishedPayload:
    action: str = ""
    success: bool = False
    message: str = ""


# ---------------------------------------------------------------------------
# 事件类
# ---------------------------------------------------------------------------


class _DaplinkEvent(QEvent):
    EVENT_TYPE = _new_event_type()

    def __init__(self, payload=None):
        super().__init__(self.EVENT_TYPE)
        self.payload = payload


class DaplinkLogEvent(_DaplinkEvent):
    EVENT_TYPE = _new_event_type()

    def __init__(self, text: str = "", level: str = "info"):
        super().__init__(type("LogPayload", (), {"text": text, "level": level})())


class DaplinkMessageEvent(_DaplinkEvent):
    EVENT_TYPE = _new_event_type()

    def __init__(self, title: str = "", content: str = "", level: str = "info"):
        super().__init__(
            type("MessagePayload", (), {"title": title, "content": content, "level": level})()
        )


class DaplinkStateEvent(_DaplinkEvent):
    EVENT_TYPE = _new_event_type()

    def __init__(self, busy: bool = False):
        super().__init__(type("StatePayload", (), {"busy": busy})())


class DaplinkProbesEvent(_DaplinkEvent):
    EVENT_TYPE = _new_event_type()

    def __init__(self, probes: list[DaplinkProbeInfo]):
        super().__init__(type("ProbesPayload", (), {"probes": probes})())


class DaplinkEsp32PortsEvent(_DaplinkEvent):
    EVENT_TYPE = _new_event_type()

    def __init__(self, ports: list[Esp32PortInfo]):
        super().__init__(type("Esp32PortsPayload", (), {"ports": ports})())


class DaplinkTargetsEvent(_DaplinkEvent):
    EVENT_TYPE = _new_event_type()

    def __init__(self, targets: list[DaplinkTargetInfo], pack_paths: list[str]):
        super().__init__(
            type("TargetsPayload", (), {"targets": targets, "pack_paths": pack_paths})()
        )


class DaplinkDeviceInfoEvent(_DaplinkEvent):
    EVENT_TYPE = _new_event_type()

    def __init__(self, info: DaplinkDeviceInfo | None):
        super().__init__(type("DeviceInfoPayload", (), {"info": info})())


class DaplinkProgressEvent(_DaplinkEvent):
    EVENT_TYPE = _new_event_type()

    def __init__(self, percent: float = 0.0):
        super().__init__(type("ProgressPayload", (), {"percent": percent})())


class DaplinkActionFinishedEvent(_DaplinkEvent):
    EVENT_TYPE = _new_event_type()

    def __init__(self, payload: ActionFinishedPayload):
        super().__init__(payload)


class DaplinkRequestEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, payload: DaplinkRequestPayload):
        super().__init__(self.EVENT_TYPE)
        self.payload = payload


# ---------------------------------------------------------------------------
# 工具路径解析
# ---------------------------------------------------------------------------

DEFAULT_UF4_TARGET_EXE = Path(
    r"E:\PROJECT_UF4POWER\Upper\DAPLINK\tools\uf4-target\uf4-target.exe"
)


def resolve_uf4_target_exe() -> Path | None:
    """依次尝试：配置项 > 环境变量 > 内置路径 > 默认仓库路径。"""
    try:
        from config import CTX

        configured = (CTX.cfg.daplinkUf4TargetExe.value or "").strip()
        if configured and Path(configured).is_file():
            return Path(configured)
    except Exception:
        pass

    env_exe = os.environ.get("UF4_TARGET_EXE", "")
    candidates = [Path(env_exe)] if env_exe else []
    candidates += [
        Path(__file__).resolve().parent.parent.parent / "src" / "tools" / "uf4-target" / "uf4-target.exe",
        DEFAULT_UF4_TARGET_EXE,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


# ---------------------------------------------------------------------------
# UF4 内置目标表（uf4-target 支持的目标）
# ---------------------------------------------------------------------------

UF4_TARGETS: list[DaplinkTargetInfo] = [
    DaplinkTargetInfo(
        target_id="g474",
        part_number="STM32G474RBT6",
        target_name="stm32g474cbtx",
        family="STM32G4",
        flash_start="0x08000000",
        flash_size="128KB",
        ram_size="128KB",
        pack_name="UF4 STM32G4 Pack (pyOCD)",
        pack_version="1.0",
    ),
    DaplinkTargetInfo(
        target_id="f429",
        part_number="STM32F429IGT6",
        target_name="stm32f429xg",
        family="STM32F4",
        flash_start="0x08000000",
        flash_size="1MB",
        ram_size="256KB",
        pack_name="pyOCD Builtin",
        pack_version="builtin",
    ),
    DaplinkTargetInfo(
        target_id="esp32",
        part_number="ESP32",
        target_name="esp32",
        family="ESP32",
        flash_start="0x10000",
        flash_size="4MB",
        ram_size="520KB",
        pack_name="UF4 Builtin (uf4-target)",
        pack_version="1.0",
    ),
]

def _target_info_by_id(target_id: str) -> DaplinkTargetInfo | None:
    for item in UF4_TARGETS:
        if item.target_id == target_id:
            return item
    return None


# ---------------------------------------------------------------------------
# 子进程执行辅助
# ---------------------------------------------------------------------------


class CommandFailed(RuntimeError):
    pass


def _run_command(
    args: list[str | os.PathLike[str]],
    log_cb,
    timeout: float = 30.0,
) -> str:
    """运行子进程，逐行回传日志；返回合并输出。"""
    command_args = [os.fspath(arg) for arg in args]
    command_text = " ".join(command_args)
    log_cb(command_text, "command")
    try:
        proc = subprocess.Popen(
            command_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        raise CommandFailed(f"无法启动进程 {command_args[0]}: {exc}") from exc

    lines: list[str] = []
    deadline = time.monotonic() + timeout
    while True:
        line = proc.stdout.readline()
        if line:
            text = line.decode("utf-8", errors="replace").rstrip("\r\n")
            lines.append(text)
            log_cb(text, "info")
            continue
        if proc.poll() is not None:
            break
        if time.monotonic() > deadline:
            proc.kill()
            raise CommandFailed(f"命令超时（>{timeout:.0f}s）: {command_text}")
        time.sleep(0.02)

    if proc.returncode != 0:
        raise CommandFailed(f"命令退出码 {proc.returncode}: {command_text}")
    return "\n".join(lines)


def _parse_frequency_khz(text: str) -> int:
    """页面频率输入 -> uf4-target probe-idcode clock (kHz)。

    纯数字按 Hz（100000 -> 100 kHz），支持 4M / 4000K 写法。
    """
    raw = (text or "").strip()
    if not raw:
        return 1000
    match = re.match(r"^\s*(\d+(?:\.\d+)?)\s*([kKmM]?)\s*$", raw)
    if not match:
        return 1000
    value = float(match.group(1))
    unit = match.group(2).lower()
    if unit == "k":
        return max(1, int(round(value)))
    if unit == "m":
        return max(1, int(round(value * 1000)))
    return max(1, int(round(value / 1000)))


def _parse_frequency_hz(text: str) -> int:
    """页面频率输入 -> pyOCD SWD/JTAG frequency (Hz)。"""
    raw = (text or "").strip()
    if not raw:
        return 1_000_000
    match = re.match(r"^\s*(\d+(?:\.\d+)?)\s*([kKmM]?)\s*$", raw)
    if not match:
        return 1_000_000
    value = float(match.group(1))
    unit = match.group(2).lower()
    if unit == "k":
        return max(1, int(round(value * 1000)))
    if unit == "m":
        return max(1, int(round(value * 1_000_000)))
    return max(1, int(round(value)))


def _parse_int_text(text: str, default: int, label: str) -> int:
    raw = (text or "").strip()
    if not raw:
        return default
    try:
        return int(raw, 0)
    except ValueError as exc:
        raise CommandFailed(f"{label} 无效: {raw}") from exc


def _windows_bus_reported_port_descriptions(port_devices: list[str]) -> dict[str, str]:
    if sys.platform != "win32":
        return {}

    wanted_ports = sorted({port.upper() for port in port_devices if port})
    if not wanted_ports:
        return {}

    try:
        proc = subprocess.run(
            ["pnputil", "/enum-devices", "/class", "Ports", "/properties"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=5.0,
        )
    except Exception:
        return {}

    if proc.returncode != 0 or not proc.stdout.strip():
        return {}

    result: dict[str, str] = {}
    for port in wanted_ports:
        port_match = re.search(rf"\({re.escape(port)}\)", proc.stdout, re.IGNORECASE)
        if not port_match:
            continue
        next_device_match = re.search(
            r"(?m)^Instance ID:\s+",
            proc.stdout[port_match.end():],
        )
        block_end = (
            port_match.end() + next_device_match.start()
            if next_device_match
            else len(proc.stdout)
        )
        block = proc.stdout[port_match.start():block_end]
        property_match = re.search(
            r"DEVPKEY_Device_BusReportedDeviceDesc\s+\[[^\]]+\]:\s*\r?\n\s*(.+)",
            block,
        )
        if property_match:
            result[port] = property_match.group(1).strip()
    return result


def _local_pack_paths() -> list[Path]:
    try:
        from config import CTX

        pack_dir = CTX.dirs.McuPackDir
    except Exception:
        pack_dir = Path(__file__).resolve().parent.parent.parent / "src" / "tools" / "pack"

    if not pack_dir.is_dir():
        return []
    return sorted(pack_dir.glob("*.pack"))


def _pyocd_pack_args_for_target(target: DaplinkTargetInfo) -> list[str]:
    if target.target_id != "g474":
        return []

    for pack in _local_pack_paths():
        name = pack.name.lower()
        if "g4" in name or "g474" in name:
            return ["--pack", str(pack)]
    return []


# ---------------------------------------------------------------------------
# 后台执行线程：一次请求一个线程
# ---------------------------------------------------------------------------


class _DaplinkWorker(QThread):
    sig_log = pyqtSignal(str, str)
    sig_message = pyqtSignal(str, str, str)
    sig_state = pyqtSignal(bool)
    sig_probes = pyqtSignal(list)
    sig_esp32_ports = pyqtSignal(list)
    sig_targets = pyqtSignal(list, list)
    sig_device_info = pyqtSignal(object)
    sig_progress = pyqtSignal(float)
    sig_finished = pyqtSignal(object)

    def __init__(self, payload: DaplinkRequestPayload, parent=None):
        super().__init__(parent)
        self._payload = payload

    def _log(self, text: str, level: str = "info") -> None:
        self.sig_log.emit(text, level)

    def _command(self, args: list[str], timeout: float = 30.0) -> str:
        return _run_command(args, self._log, timeout=timeout)

    # ---- 动作实现 ----

    def _scan_probes(self) -> None:
        exe = resolve_uf4_target_exe()
        if exe is None:
            raise CommandFailed("未找到 uf4-target.exe，请检查配置或 DAPLINK 仓库路径。")

        try:
            output = self._command([exe, "list"], timeout=15.0)
        except CommandFailed:
            output = ""

        probes: list[DaplinkProbeInfo] = []
        pattern = re.compile(
            r"\[(\d+)\]\s+VID:PID=([0-9A-Fa-f]{4}):([0-9A-Fa-f]{4})"
            r"\s+serial=(\S*)\s+product=(\S*)\s+in=\d+\s+out=\d+"
        )
        for line in output.splitlines():
            match = pattern.search(line)
            if not match:
                continue
            probes.append(
                DaplinkProbeInfo(
                    index=int(match.group(1)),
                    uid=match.group(4),
                    description=match.group(5),
                    product_name=match.group(5),
                    vendor_name="UF4",
                )
            )
        self.sig_probes.emit(probes)

    def _scan_esp32_ports(self) -> None:
        try:
            from serial.tools import list_ports
        except Exception as exc:  # noqa: BLE001
            raise CommandFailed(f"无法加载 pyserial 串口扫描模块: {exc}") from exc

        serial_ports = list(list_ports.comports())
        bus_descriptions = _windows_bus_reported_port_descriptions(
            [str(port.device) for port in serial_ports]
        )
        ports: list[Esp32PortInfo] = []
        for port in serial_ports:
            bus_reported = bus_descriptions.get(str(port.device).upper(), "")
            ports.append(
                Esp32PortInfo(
                    device=port.device,
                    description=port.description,
                    hwid=port.hwid,
                    bus_reported_description=bus_reported,
                )
            )

        def sort_key(item: Esp32PortInfo) -> tuple[int, str]:
            text = f"{item.bus_reported_description} {item.description} {item.hwid}".lower()
            is_uf4 = "cafe:401b" in text or "vid:pid=cafe:401b" in text
            is_esp32 = "esp32" in text
            is_cdc3 = "x.3" in text or "mi_03" in text
            is_cdc1 = "x.1" in text or "mi_01" in text
            if is_esp32:
                rank = 0
            elif is_uf4 and is_cdc3:
                rank = 1
            elif is_uf4 and is_cdc1:
                rank = 2
            elif is_uf4:
                rank = 3
            else:
                rank = 4
            return (rank, item.device)

        ports.sort(key=sort_key)
        self.sig_esp32_ports.emit(ports)
        if ports:
            summaries = []
            for port in ports:
                label = port.bus_reported_description or port.description or port.hwid
                summaries.append(f"{port.device} {label}".strip())
            self._log("ESP32 串口扫描: " + ", ".join(summaries))
        else:
            self._log("ESP32 串口扫描: 未发现可用串口", "error")

    def _load_targets(self) -> None:
        pack_paths = [str(path) for path in _local_pack_paths()]
        self.sig_targets.emit(UF4_TARGETS, pack_paths or ["pyOCD builtin targets"])

    def _read_current_target(self) -> str | None:
        """uf4-target get -> 'none' / 'g474' / 'f429'。"""
        exe = resolve_uf4_target_exe()
        if exe is None:
            return None
        try:
            output = self._command([exe, "get"], timeout=10.0)
        except CommandFailed:
            return None
        match = re.search(r"Current target:\s*(\w+)", output)
        if not match:
            return None
        name = match.group(1).lower()
        return {"none": "none", "g474": "g474", "f429": "f429"}.get(name, name)

    def _resolve_target(self, config: DaplinkConnectConfig | None) -> DaplinkTargetInfo | None:
        target_name = (config.target_name if config else "") or ""
        if not target_name:
            return None
        key = target_name.lower()
        for item in UF4_TARGETS:
            if key in (item.target_id, item.target_name, item.part_number.lower()):
                return item
        raise CommandFailed(f"未知目标: {target_name}")

    def _connect(self, config: DaplinkConnectConfig | None) -> None:
        exe = resolve_uf4_target_exe()
        if exe is None:
            raise CommandFailed("未找到 uf4-target.exe，请检查配置或 DAPLINK 仓库路径。")

        target = self._resolve_target(config)
        current = self._read_current_target()
        self._log(f"当前 uf4-target 目标: {current or '未知'}")

        if target is not None and current != target.target_id:
            self._log(f"切换 SWD 目标到 {target.part_number} ({target.target_id})")
            self._command([exe, "set", target.target_id], timeout=10.0)
            time.sleep(0.15)
        elif target is None:
            target = _target_info_by_id(current) if current and current != "none" else UF4_TARGETS[0]

        clock_khz = _parse_frequency_khz((config.frequency if config else "") or "100000")
        probe_args = [exe, "probe-idcode", "--clock-khz", str(clock_khz), "--repeat", "1"]
        if target is not None:
            probe_args += ["--target", target.target_id]
        idcode = "--"
        try:
            output = self._command(probe_args, timeout=15.0)
            match = re.search(r"IDCODE\[0\]:\s*0x([0-9A-Fa-f]{8})", output)
            if match:
                idcode = "0x" + match.group(1).upper()
        except CommandFailed as exc:
            self._log(str(exc), "error")

        info = DaplinkDeviceInfo(
            probe_uid="UF4-F401" if current is not None else "--",
            probe_description=f"UF4 F401 CMSIS-DAP | IDCODE {idcode}",
            vendor="UF4",
            product="UF4 F401 CMSIS-DAP 2CDC",
            target_name=target.target_name if target else "--",
            part_number=target.part_number if target else "--",
            family=target.family if target else "--",
            flash_start=target.flash_start if target else "--",
            flash_size=target.flash_size if target else "--",
            ram_size=target.ram_size if target else "--",
            pack_name=target.pack_name if target else "--",
            pack_version=target.pack_version if target else "--",
            idcode=idcode,
        )
        self.sig_device_info.emit(info)
        if idcode == "--":
            raise CommandFailed("SWD 探测失败：未读到目标 IDCODE，请检查目标选择与接线。")

    def _download(self, payload: DaplinkRequestPayload) -> None:
        file_path = payload.file_path
        if not file_path or not Path(file_path).is_file():
            raise CommandFailed(f"固件文件不存在: {file_path}")

        exe = resolve_uf4_target_exe()
        if exe is None:
            raise CommandFailed("未找到 uf4-target.exe，请检查配置或 DAPLINK 仓库路径。")

        target = self._resolve_target(payload.connect)
        if target is None:
            raise CommandFailed("下载前请先在页面选择目标芯片（STM32G474 / STM32F429）。")

        if target.target_id == "esp32":
            raise CommandFailed(
                "ESP32 请使用本页面下方的 ESP32 烧录卡片，通过 esptool 串口烧录。"
            )

        current = self._read_current_target()
        if current != target.target_id:
            self._log(f"切换 SWD 目标到 {target.part_number} ({target.target_id})")
            self._command([exe, "set", target.target_id], timeout=10.0)
            time.sleep(0.15)

        frequency_hz = _parse_frequency_hz(
            (payload.connect.frequency if payload.connect else "") or "100000"
        )
        suffix = Path(file_path).suffix.lower()
        file_format = suffix.lstrip(".")
        if file_format == "axf":
            file_format = "elf"
        if file_format not in {"bin", "hex", "elf"}:
            raise CommandFailed(f"不支持的固件格式: {suffix}")

        pyocd_args = [
            sys.executable,
            "-m",
            "pyocd",
            "load",
            file_path,
            "-t",
            target.target_name,
            "-f",
            str(frequency_hz),
            "-M",
            (payload.connect.connect_mode if payload.connect else "") or "under-reset",
            "-e",
            payload.erase_mode or "sector",
            "--format",
            file_format,
        ]

        probe_uid = (payload.connect.probe_uid if payload.connect else "") or ""
        if probe_uid:
            pyocd_args += ["-u", probe_uid]

        if suffix == ".bin":
            base_addr = (payload.base_address or "").strip() or "0x08000000"
            try:
                int(base_addr, 0)
            except ValueError as exc:
                raise CommandFailed(f"Bin 起始地址无效: {base_addr}") from exc
            pyocd_args += ["-a", base_addr]
        if payload.trust_crc:
            pyocd_args.append("--trust-crc")
        if not payload.reset_after_download:
            pyocd_args.append("--no-reset")

        pyocd_args += _pyocd_pack_args_for_target(target)

        if target.target_id == "g474" and "--pack" not in pyocd_args:
            raise CommandFailed(
                "未找到 STM32G4 pyOCD Pack，请把 STM32G4 .pack 放到 src/tools/pack。"
            )

        self._log(f"pyOCD 下载开始: {Path(file_path).name} -> {target.part_number}")
        self.sig_progress.emit(10.0)
        output = self._command(pyocd_args, timeout=180.0)
        self.sig_progress.emit(95.0)

        output_lower = output.lower()
        if not any(marker in output_lower for marker in ("erased", "programmed", "verified")):
            raise CommandFailed("pyOCD 输出异常：未检测到擦除/写入/校验信息。")
        self._log(f"下载完成: {Path(file_path).name} -> {target.part_number}")
        self.sig_progress.emit(100.0)

    def _esp32_boot(self) -> None:
        exe = resolve_uf4_target_exe()
        if exe is None:
            raise CommandFailed("未找到 uf4-target.exe，请检查配置或 DAPLINK 仓库路径。")
        self._log("ESP32 进入下载模式")
        self._command([exe, "esp32-boot"], timeout=10.0)
        time.sleep(0.35)

    def _esp32_reset(self) -> None:
        exe = resolve_uf4_target_exe()
        if exe is None:
            raise CommandFailed("未找到 uf4-target.exe，请检查配置或 DAPLINK 仓库路径。")
        self._log("ESP32 复位运行")
        self._command([exe, "esp32-reset"], timeout=10.0)

    def _esp32_flash(self, payload: DaplinkRequestPayload) -> None:
        file_path = payload.file_path
        if not file_path or not Path(file_path).is_file():
            raise CommandFailed(f"ESP32 固件文件不存在: {file_path}")

        port = (payload.esp_port or "").strip()
        if not port:
            raise CommandFailed("请先选择 ESP32 串口。")

        baud = _parse_int_text(payload.esp_baud, 921600, "ESP32 波特率")
        address = _parse_int_text(payload.esp_address, 0x10000, "ESP32 烧录地址")
        flash_mode = (payload.esp_flash_mode or "dio").strip() or "dio"
        flash_freq = (payload.esp_flash_freq or "40m").strip() or "40m"
        flash_size = (payload.esp_flash_size or "detect").strip() or "detect"

        self._esp32_boot()
        self.sig_progress.emit(5.0)

        if payload.esp_erase:
            erase_args = [
                sys.executable,
                "-m",
                "esptool",
                "--chip",
                "esp32",
                "--port",
                port,
                "--baud",
                str(baud),
                "--before",
                "no-reset",
                "--after",
                "no-reset",
                "erase-flash",
            ]
            self._log("ESP32 擦除 Flash")
            self._command(erase_args, timeout=120.0)
            self.sig_progress.emit(20.0)

        flash_args = [
            sys.executable,
            "-m",
            "esptool",
            "--chip",
            "esp32",
            "--port",
            port,
            "--baud",
            str(baud),
            "--before",
            "no-reset",
            "--after",
            "no-reset",
            "write-flash",
            "-z",
            "--flash-mode",
            flash_mode,
            "--flash-freq",
            flash_freq,
            "--flash-size",
            flash_size,
            hex(address),
            file_path,
        ]
        self._log(f"ESP32 esptool 烧录开始: {Path(file_path).name} -> {port} @ {hex(address)}")
        self.sig_progress.emit(25.0)
        output = self._command(flash_args, timeout=240.0)
        output_lower = output.lower()
        if not any(marker in output_lower for marker in ("hash of data verified", "hard resetting", "leaving", "wrote")):
            raise CommandFailed("esptool 输出异常：未检测到写入/校验完成信息。")

        if payload.reset_after_download:
            self._esp32_reset()
        self.sig_progress.emit(100.0)
        self._log("ESP32 烧录完成")

    # ---- 线程主体 ----

    def run(self) -> None:
        payload = self._payload
        action = payload.action
        self.sig_state.emit(True)
        try:
            if action == "scan_probes":
                self._scan_probes()
            elif action == "load_targets":
                self._load_targets()
            elif action == "scan_esp32_ports":
                self._scan_esp32_ports()
            elif action == "connect":
                self._connect(payload.connect)
            elif action == "download":
                self._download(payload)
            elif action == "esp32_flash":
                self._esp32_flash(payload)
            elif action == "esp32_reset":
                self._esp32_reset()
            else:
                raise CommandFailed(f"未知动作: {action}")
        except CommandFailed as exc:
            self.sig_message.emit("操作失败", str(exc), "error")
            self.sig_finished.emit(
                ActionFinishedPayload(action=action, success=False, message=str(exc))
            )
            return
        except Exception as exc:  # noqa: BLE001
            self._log(f"内部错误: {exc}", "error")
            self.sig_finished.emit(
                ActionFinishedPayload(action=action, success=False, message=str(exc))
            )
            return

        self.sig_finished.emit(
            ActionFinishedPayload(action=action, success=True, message="ok")
        )


# ---------------------------------------------------------------------------
# 会话对象（页面直接交互的入口）
# ---------------------------------------------------------------------------


class DaplinkPyocdSession(QObject):
    """接收页面的请求事件，在后台线程执行 uf4-target/pyOCD 逻辑。"""

    def __init__(self, _event_receiver=None, parent=None):
        super().__init__(parent)
        self._event_receiver = _event_receiver
        self.is_busy = False
        self._worker: _DaplinkWorker | None = None

    def customEvent(self, event: QEvent) -> None:
        if not isinstance(event, DaplinkRequestEvent):
            return
        if self.is_busy:
            self._post(DaplinkMessageEvent("忙", "上一操作尚未完成，请稍候。", "warning"))
            return

        self.is_busy = True
        self._post(DaplinkStateEvent(busy=True))
        self._worker = _DaplinkWorker(event.payload, parent=self)
        self._worker.sig_log.connect(self._on_log)
        self._worker.sig_message.connect(self._on_message)
        self._worker.sig_state.connect(self._on_state)
        self._worker.sig_probes.connect(self._on_probes)
        self._worker.sig_esp32_ports.connect(self._on_esp32_ports)
        self._worker.sig_targets.connect(self._on_targets)
        self._worker.sig_device_info.connect(self._on_device_info)
        self._worker.sig_progress.connect(self._on_progress)
        self._worker.sig_finished.connect(self._on_finished)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _post(self, event: QEvent) -> None:
        receiver = self._event_receiver
        if receiver is not None:
            QCoreApplication.postEvent(receiver, event)

    def _on_log(self, text: str, level: str) -> None:
        self._post(DaplinkLogEvent(text, level))

    def _on_message(self, title: str, content: str, level: str) -> None:
        self._post(DaplinkMessageEvent(title, content, level))

    def _on_state(self, busy: bool) -> None:
        self._post(DaplinkStateEvent(busy))

    def _on_probes(self, probes: list) -> None:
        self._post(DaplinkProbesEvent(probes))

    def _on_esp32_ports(self, ports: list) -> None:
        self._post(DaplinkEsp32PortsEvent(ports))

    def _on_targets(self, targets: list, pack_paths: list) -> None:
        self._post(DaplinkTargetsEvent(targets, pack_paths))

    def _on_device_info(self, info) -> None:
        self._post(DaplinkDeviceInfoEvent(info))

    def _on_progress(self, percent: float) -> None:
        self._post(DaplinkProgressEvent(percent))

    def _on_finished(self, payload: ActionFinishedPayload) -> None:
        self.is_busy = False
        self._post(DaplinkStateEvent(busy=False))
        self._post(DaplinkActionFinishedEvent(payload))

    def shutdown(self) -> None:
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.wait(3000)
