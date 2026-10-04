# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
import threading
import time

from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from app.protocol.uf4com import (
    Uf4Command,
    Uf4Error,
    Uf4Flag,
    Uf4FrameParser,
    build_frame,
    encode_tv,
    iter_tv_items,
    parse_error_payload,
    response_cmd_for,
)


UF4_REQUEST_TIMEOUT_S = 0.75
UF4_SAVE_TIMEOUT_S = 3.0
UF4_LINK_HEARTBEAT_MS = 200


class Uf4ProtocolError(RuntimeError):
    def __init__(self, code, command: int):
        self.code = code
        self.command = int(command)
        if code == Uf4Error.DEVICE_BUSY:
            reason = "设备忙：输出正在由另一条通信链路控制，或参数保存尚未完成"
        else:
            reason = "设备拒绝请求"
        name = code.name if isinstance(code, Uf4Error) else "UNKNOWN_ERROR"
        value = f"0x{int(code):04X}" if code is not None else "无错误码"
        super().__init__(f"{reason} ({name}, {value}, CMD=0x{self.command:02X})")


@dataclass(frozen=True)
class SerialConfig:
    port: str = ""
    baudrate: int = 115200


class SerialSession(QObject):
    """Blocking serial endpoint used exclusively by the power-client thread."""

    def __init__(self, config: SerialConfig | None = None, _event_receiver=None, parent=None):
        super().__init__(parent)
        self.config = config or SerialConfig()
        self.cfg = self.config
        self._serial = None
        self._lock = threading.Lock()
        self.is_open = False

    def set_event_receiver(self, _receiver) -> None:
        return None

    def open(self) -> bool:
        if self.is_open:
            return True
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("缺少 pyserial，无法打开串口") from exc
        port = self.config.port.strip()
        if not port:
            raise ValueError("串口不能为空")
        self._serial = serial.Serial(
            port=port,
            baudrate=self.config.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.1,
            write_timeout=1.0,
        )
        self.is_open = True
        return True

    def close(self) -> None:
        with self._lock:
            serial_port, self._serial = self._serial, None
            self.is_open = False
            if serial_port is not None:
                serial_port.close()

    def reset_input_buffer(self) -> None:
        with self._lock:
            if not self.is_open or self._serial is None:
                raise ConnectionError("串口未连接")
            self._serial.reset_input_buffer()

    def read(self, size: int = 2048) -> bytes:
        with self._lock:
            if not self.is_open or self._serial is None:
                raise ConnectionError("串口未连接")
            return self._serial.read(max(1, min(int(size), self._serial.in_waiting)))

    def write(self, data: bytes) -> int:
        with self._lock:
            if not self.is_open or self._serial is None:
                raise ConnectionError("串口未连接")
            count = self._serial.write(data)
            self._serial.flush()
            return count


@dataclass(frozen=True)
class PowerStatus:
    vin_v: float = 0.0
    iin_a: float = 0.0
    pin_w: float = 0.0
    vout_v: float = 0.0
    iout_a: float = 0.0
    pout_w: float = 0.0
    efficiency: float = 0.0
    core_temp_c: float = 0.0
    board_temp_c: float = 0.0
    set_voltage_limit_mv: int = 0
    set_current_limit_ma: int = 0
    ovp_set_value_v: float = 0.0
    ocp_set_value_a: float = 0.0
    otp_set_value_c: float = 0.0
    fan_set_value: int = 0
    fan_speed: int = 0
    power_enabled: bool = False
    power_state: int = 0
    fault_state: int = 0
    state_machine_flag_bits: int = 0
    duty_permille: int = 0
    mode_name: str = "未连接"
    topology_name: str = "未连接"
    state_flag_name: str = "IDLE"
    pwm_a_compare: int = 0
    pwm_d_compare: int = 0
    ovp_set_value_mv: int = 0
    ocp_set_value_ma: int = 0
    otp_set_value_mc: int = 0


class F4CPPowerClient(QObject):
    """UF4COM V5 client for the G474 power stage on a direct PC UART link."""

    connectionChanged = pyqtSignal(bool)
    statusUpdated = pyqtSignal(object)
    errorOccurred = pyqtSignal(str)
    outputLimitsWritten = pyqtSignal()
    protectionValuesWritten = pyqtSignal()
    powerStateWritten = pyqtSignal(bool)
    faultClearWritten = pyqtSignal()
    parametersRead = pyqtSignal(object)
    parametersSaved = pyqtSignal()
    writeTransactionFinished = pyqtSignal()
    communicationFailure = pyqtSignal(str)

    _STATUS_IDS = (
        0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10,
        0x11, 0x12, 0x14, 0x15, 0x16, 0x17, 0x1E, 0x22, 0x23,
        0x29, 0x2A, 0x2B,
        0x26, 0x27, 0x32, 0x45, 0x4B, 0x4C, 0x4D, 0x4E, 0x50,
    )
    _TOPOLOGY_NAMES = ("BUCK", "BOOST")
    _STATE_NAMES = ("SELF_CHECK", "IDLE", "SOFT_START", "RUN", "STOPPING", "DIRECTION_SWITCH", "FAULT")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_connected = False
        self.is_busy = False
        self._session: SerialSession | None = None
        self._parser = Uf4FrameParser()
        self._seq = 0
        self._poll_timer: QTimer | None = None
        self._heartbeat_timer: QTimer | None = None

    def pretty_print_status(self, status: PowerStatus) -> str:
        return (
            f"VIN={status.vin_v:.3f}V VOUT={status.vout_v:.3f}V "
            f"IIN={status.iin_a:.3f}A IOUT={status.iout_a:.3f}A "
            f"{status.topology_name} {status.state_flag_name} fault=0x{status.fault_state:04X}"
        )

    @pyqtSlot(object)
    def attach_session(self, session) -> None:
        if not getattr(session, "is_open", False):
            self._fail("串口未打开")
            return
        self._session = session
        self._parser.reset()
        self.is_connected = True
        if self._heartbeat_timer is None:
            self._heartbeat_timer = QTimer(self)
            self._heartbeat_timer.timeout.connect(self._keep_link_alive)
        self._heartbeat_timer.start(UF4_LINK_HEARTBEAT_MS)
        self.connectionChanged.emit(True)

    @pyqtSlot()
    def detach_session(self) -> None:
        self.stop_polling()
        if self._heartbeat_timer is not None:
            self._heartbeat_timer.stop()
        self._session = None
        was_connected = self.is_connected
        self.is_connected = False
        self.is_busy = False
        if was_connected:
            self.connectionChanged.emit(False)

    @pyqtSlot()
    def read_status(self) -> None:
        if not self.is_connected:
            return
        try:
            payload = b"".join(encode_tv(data_id) for data_id in self._STATUS_IDS)
            frame = self._request(Uf4Command.READ_REQ, payload)
            values = {item.id: int(item.value or 0) for item in iter_tv_items(frame.data)}
            self.statusUpdated.emit(self._make_status(values))
        except Exception as exc:
            self._fail(exc)

    @pyqtSlot(int, int, bool)
    def write_output_limits(self, voltage_centi_v: int, current_centi_a: int, enabled: bool) -> None:
        success = self._write_values(
            ((0x11, voltage_centi_v), (0x12, current_centi_a), (0x50, int(enabled)))
        )
        if success:
            self.outputLimitsWritten.emit()

    @pyqtSlot(int, int, int, int)
    def write_protection_values(self, ovp_centi_v: int, ocp_centi_a: int, otp_centi_c: int, fan_permille: int) -> None:
        success = self._write_values(((0x32, ovp_centi_v), (0x22, ocp_centi_a), (0x1E, otp_centi_c), (0x27, fan_permille)))
        if success:
            self.protectionValuesWritten.emit()

    @pyqtSlot(bool)
    def write_power_state(self, enabled: bool) -> None:
        if self._write_values(((0x50, int(enabled)),)):
            self.powerStateWritten.emit(enabled)

    @pyqtSlot()
    def clear_fault(self) -> None:
        if not self.is_connected:
            self._fail("串口会话未连接")
            self.writeTransactionFinished.emit()
            return
        try:
            frame = self._request(Uf4Command.READ_REQ, encode_tv(0x15))
            values = {item.id: int(item.value or 0) for item in iter_tv_items(frame.data)}
            if values.get(0x15) != 6:
                raise RuntimeError("设备未处于 FAULT 状态，无需清除故障")
            # The firmware clears a latched fault only on an enable 1 -> 0 edge.
            try:
                self._request(Uf4Command.WRITE_REQ, encode_tv(0x50, 1))
            finally:
                self._request(Uf4Command.WRITE_REQ, encode_tv(0x50, 0))
            deadline = time.monotonic() + 0.2
            while True:
                frame = self._request(Uf4Command.READ_REQ, encode_tv(0x15) + encode_tv(0x16) + encode_tv(0x50))
                values = {item.id: int(item.value or 0) for item in iter_tv_items(frame.data)}
                if values.get(0x15) == 1 and values.get(0x16) == 0 and values.get(0x50) == 0:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("故障仍然存在，请检查故障原因和保护状态")
                time.sleep(0.01)
        except Exception as exc:
            self._fail(exc)
        else:
            self.faultClearWritten.emit()
        finally:
            self.writeTransactionFinished.emit()

    @pyqtSlot(object)
    def read_parameters(self, ids) -> None:
        if not self.is_connected:
            self._fail("串口会话未连接")
            return
        try:
            payload = b"".join(encode_tv(int(data_id)) for data_id in ids)
            frame = self._request(Uf4Command.READ_REQ, payload)
            values = {item.id: int(item.value or 0) for item in iter_tv_items(frame.data)}
            self.parametersRead.emit(values)
        except Exception as exc:
            self._fail(exc)

    @pyqtSlot(object)
    def write_parameters(self, values) -> None:
        pairs = tuple((int(data_id), int(value)) for data_id, value in values)
        if not self.is_connected:
            self._fail("串口会话未连接")
            self.writeTransactionFinished.emit()
            return
        try:
            if pairs:
                payload = b"".join(encode_tv(data_id, value) for data_id, value in pairs)
                self._request(Uf4Command.WRITE_REQ, payload)
            self._request(Uf4Command.SAVE_REQ, b"")
        except Exception as exc:
            self._fail(exc)
        else:
            self.parametersSaved.emit()
        finally:
            self.writeTransactionFinished.emit()

    @pyqtSlot(int)
    def start_polling(self, interval_ms: int) -> None:
        if self._poll_timer is None:
            self._poll_timer = QTimer(self)
            self._poll_timer.timeout.connect(self.read_status)
        self._poll_timer.start(max(100, int(interval_ms)))

    @pyqtSlot()
    def stop_polling(self) -> None:
        if self._poll_timer is not None:
            self._poll_timer.stop()

    @pyqtSlot()
    def shutdown(self) -> None:
        self.detach_session()

    def _write_values(self, values: tuple[tuple[int, int], ...]) -> bool:
        if not self.is_connected:
            self._fail("串口会话未连接")
            return False
        try:
            payload = b"".join(encode_tv(data_id, value) for data_id, value in values)
            self._request(Uf4Command.WRITE_REQ, payload)
        except Exception as exc:
            self._fail(exc)
            return False
        finally:
            self.writeTransactionFinished.emit()
        return True

    def _request(self, command: int, payload: bytes):
        if self._session is None or not self._session.is_open:
            raise ConnectionError("串口会话未连接")
        if self.is_busy:
            raise RuntimeError("协议请求进行中")
        self.is_busy = True
        try:
            self._seq = (self._seq + 1) & 0xFF
            request = build_frame(command, self._seq, payload, Uf4Flag.ACK_REQ)
            self._parser.reset()
            self._session.reset_input_buffer()
            self._session.write(request)
            expected = response_cmd_for(command)
            timeout = UF4_SAVE_TIMEOUT_S if command == Uf4Command.SAVE_REQ else UF4_REQUEST_TIMEOUT_S
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                received = self._session.read(2048)
                for reply in self._parser.feed(received):
                    if reply.seq != self._seq or reply.cmd != expected or not reply.is_ack:
                        continue
                    if reply.is_error:
                        raise Uf4ProtocolError(parse_error_payload(reply.data), command)
                    return reply
            raise TimeoutError("等待 G474 UF4COM 响应超时")
        finally:
            self.is_busy = False

    def _keep_link_alive(self) -> None:
        if not self.is_connected or self.is_busy:
            return
        try:
            self._request(Uf4Command.READ_REQ, encode_tv(0x50))
        except Exception as exc:
            self._fail(exc)

    def _make_status(self, values: dict[int, int]) -> PowerStatus:
        get = values.get
        vin = get(0x0A, 0) / 100.0
        iin = get(0x0B, 0) / 100.0
        vout = get(0x0C, 0) / 100.0
        iout = get(0x0D, 0) / 100.0
        topology = get(0x45, 0)
        state = get(0x15, 0)
        return PowerStatus(
            vin_v=vin, iin_a=iin, pin_w=vin * iin,
            vout_v=vout, iout_a=iout, pout_w=vout * iout,
            efficiency=0.0 if vin * iin <= 0 else vout * iout / (vin * iin) * 100.0,
            core_temp_c=get(0x0E, 0) / 100.0,
            board_temp_c=get(0x0F, 0) / 100.0,
            set_voltage_limit_mv=get(0x11, 0), set_current_limit_ma=get(0x12, 0),
            ovp_set_value_v=get(0x32, 0) / 100.0, ocp_set_value_a=get(0x22, 0) / 100.0,
            otp_set_value_c=get(0x1E, 0) / 100.0,
            fan_set_value=get(0x27, 0), fan_speed=get(0x26, 0),
            power_enabled=get(0x50, 0) == 1,
            power_state=state, fault_state=get(0x16, 0),
            state_machine_flag_bits=get(0x17, 0), duty_permille=get(0x23, 0),
            mode_name="CV" if get(0x14, 0) else "CC",
            topology_name=self._TOPOLOGY_NAMES[topology] if topology < len(self._TOPOLOGY_NAMES) else f"UNKNOWN({topology})",
            state_flag_name=self._STATE_NAMES[state] if state < len(self._STATE_NAMES) else f"UNKNOWN({state})",
            ovp_set_value_mv=get(0x32, 0), ocp_set_value_ma=get(0x22, 0), otp_set_value_mc=get(0x1E, 0),
        )

    def _fail(self, error: str | Exception) -> None:
        message = str(error)
        self.errorOccurred.emit(message)
        if not isinstance(error, Uf4ProtocolError) or error.code != Uf4Error.DEVICE_BUSY:
            self.communicationFailure.emit(message)
