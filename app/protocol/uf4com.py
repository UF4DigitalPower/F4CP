# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Callable, Iterable


UF4_SOF1 = 0xAA
UF4_SOF2 = 0x55

UF4_MAX_DATA_LEN = 255
UF4_V5_HEADER_LEN = 6
UF4_CRC_LEN = 2
UF4_MAX_FRAME_LEN = UF4_V5_HEADER_LEN + UF4_MAX_DATA_LEN + UF4_CRC_LEN

UF4_DEFAULT_ACK_TIMEOUT_MS = 50
UF4_DEFAULT_ACK_RETRIES = 3
UF4_MAX_PENDING_REQUESTS = 8
UF4_TV_SIZE = 3


class Uf4Command(IntEnum):
    READ_REQ = 0x01
    READ_RSP = 0x81
    WRITE_REQ = 0x02
    WRITE_RSP = 0x82
    STREAM_START_REQ = 0x10
    STREAM_START_RSP = 0x90
    STREAM_STOP_REQ = 0x11
    STREAM_STOP_RSP = 0x91
    SAVE_REQ = 0x12
    SAVE_RSP = 0x92
    STREAM_DATA = 0x15


class Uf4Flag(IntEnum):
    ACK_REQ = 0x01
    ACK_FRAME = 0x02
    ERROR = 0x04


class Uf4DataId(IntEnum):
    INPUT_VOLTAGE = 0x0A
    INPUT_CURRENT = 0x0B
    OUTPUT_VOLTAGE = 0x0C
    OUTPUT_CURRENT = 0x0D
    CORE_TEMPERATURE = 0x0E
    TEMP1_TEMPERATURE = 0x0F
    TEMP2_TEMPERATURE = 0x10
    SET_VOLTAGE_LIMIT = 0x11
    SET_CURRENT_LIMIT = 0x12
    POWER_DIRECTION = 0x13
    CC_CV_MODE = 0x14
    POWER_STATE = 0x15
    FAULT_STATE = 0x16
    STATE_MACHINE_FLAG_BITS = 0x17
    STATE_MACHINE_STATE = 0x18
    INPUT_VOLTAGE_RAW = 0x19
    INPUT_CURRENT_RAW = 0x1A
    OUTPUT_VOLTAGE_RAW = 0x1B
    OUTPUT_CURRENT_RAW = 0x1C
    OTP_VALUE = 0x1D
    OTP_SET_VALUE = 0x1E
    OVP_VALUE = 0x1F
    OVP_SET_VALUE = 0x20
    OCP_VALUE = 0x21
    OCP_SET_VALUE = 0x22
    DUTY_CMD = 0x23
    PWM_A_COMPARE = 0x24
    PWM_D_COMPARE = 0x25
    FAN_SPEED = 0x26
    FAN_SET_VALUE = 0x27
    FMAC_SELFTEST_FIRST_RAW = 0x28
    LOOP_CURRENT_FEEDBACK = 0x29
    LOOP_CURRENT_REFERENCE = 0x2A
    VOLTAGE_LOOP_CURRENT_REFERENCE = 0x2B
    FMAC_SELFTEST_SECOND_RAW = 0x2C
    FMAC_DIAGNOSTIC_STAGE = 0x2D
    FMAC_DIAGNOSTIC_STATUS = 0x2E
    DAC3_CH1_OUTPUT_CODE = 0x2F
    CFG_VIN_OVP = 0x30
    CFG_VIN_UVP = 0x31
    CFG_VOUT_OVP = 0x32
    CFG_ADC_VREF = 0x33
    CFG_VIN_R_UPPER = 0x34
    CFG_VIN_R_LOWER = 0x35
    CFG_VOUT_R_UPPER = 0x36
    CFG_VOUT_R_LOWER = 0x37
    CFG_SHUNT_IN = 0x38
    CFG_SHUNT_OUT = 0x39
    CFG_GAIN_IN = 0x3A
    CFG_GAIN_OUT = 0x3B
    CFG_CURRENT_OFFSET = 0x3C
    CFG_VIN_GAIN = 0x3D
    CFG_VIN_OFFSET = 0x3E
    CFG_VOUT_GAIN = 0x3F
    CFG_VOUT_OFFSET = 0x40
    CFG_IIN_GAIN = 0x41
    CFG_IIN_OFFSET = 0x42
    CFG_IOUT_GAIN = 0x43
    CFG_IOUT_OFFSET = 0x44
    POWER_CONVERTER_MODE = 0x45
    CFG_CURRENT_KP = 0x48
    CFG_CURRENT_KI = 0x49
    CFG_CURRENT_KD = 0x4A
    POWER_DIRECTION_STATUS = 0x4B
    CONTROL_ISR_LAST_CYCLES = 0x4C
    CONTROL_ISR_MAX_CYCLES = 0x4D
    CONTROL_ISR_OVERRUN_COUNT = 0x4E
    CFG_POWER_DIRECTION_MODE = 0x4F
    OUTPUT_ENABLE = 0x50
    CFG_VOLTAGE_KP = 0x51
    CFG_VOLTAGE_KI = 0x52
    CFG_VOLTAGE_KD = 0x53
    DAC4_CH1_OUTPUT_CODE = 0x54
    SELF_CHECK_STATUS = 0x55
    LATCHED_FAULT_REASON = 0x56


class Uf4Error(IntEnum):
    OK = 0x0000
    INVALID_ID = 0x0001
    INVALID_CMD = 0x0002
    CRC = 0x0003
    INVALID_LEN = 0x0004
    WRITE_PROTECT = 0x0005
    OUT_OF_RANGE = 0x0006
    DEVICE_BUSY = 0x0007
    INTERNAL = 0x0008
    TIMEOUT = 0x0009
    NO_PENDING_SLOT = 0x000A


class Uf4AckStatus(IntEnum):
    PENDING = 0
    DONE = 1
    TIMEOUT = 2
    DROPPED = 3


class Uf4IdPermission(IntEnum):
    RO = 0
    RW = 1


class Uf4ParserState(IntEnum):
    WAIT_SOF1 = 0
    WAIT_SOF2 = 1
    WAIT_SEQ = 2
    WAIT_FLAGS = 3
    WAIT_CMD = 4
    WAIT_LEN = 5
    WAIT_DATA = 6
    WAIT_CRC_L = 7
    WAIT_CRC_H = 8


@dataclass(frozen=True)
class Uf4Frame:
    seq: int
    flags: int
    cmd: int
    data: bytes = b""

    @property
    def length(self) -> int:
        return len(self.data)

    @property
    def is_ack(self) -> bool:
        return bool(self.flags & Uf4Flag.ACK_FRAME)

    @property
    def is_error(self) -> bool:
        return bool(self.flags & Uf4Flag.ERROR)

    def to_bytes(self) -> bytes:
        return build_frame(self.cmd, self.seq, self.data, self.flags)


@dataclass(frozen=True)
class Uf4TvItem:
    id: int
    value: int | None
    raw: bytes
    data_id: Uf4DataId | None = None


@dataclass(frozen=True)
class Uf4Config:
    ack_timeout_ms: int = UF4_DEFAULT_ACK_TIMEOUT_MS
    ack_retries: int = UF4_DEFAULT_ACK_RETRIES


@dataclass
class Uf4Register:
    id: int
    value: int = 0
    permission: Uf4IdPermission = Uf4IdPermission.RO


@dataclass
class _PendingRequest:
    seq: int
    expected_cmd: int
    frame: bytes
    retries_left: int
    last_tx_ms: int
    timeout_ms: int
    active: bool = True


def _u8(value: int) -> int:
    return int(value) & 0xFF


def _u16(value: int) -> int:
    return int(value) & 0xFFFF


def crc16(data: bytes | bytearray | memoryview) -> int:
    crc = 0xFFFF
    for byte in bytes(data):
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def frame_crc(frame: Uf4Frame) -> int:
    body = bytes(
        [
            _u8(frame.seq),
            _u8(frame.flags),
            _u8(frame.cmd),
            frame.length,
        ]
    ) + frame.data
    return crc16(body)


def build_frame(
    cmd: int,
    seq: int,
    data: bytes | bytearray | memoryview | None = b"",
    flags: int = 0,
) -> bytes:
    payload = bytes(data or b"")
    if len(payload) > UF4_MAX_DATA_LEN:
        raise ValueError(f"UF4COM DATA too long: {len(payload)} > {UF4_MAX_DATA_LEN}")

    body = bytes([_u8(seq), _u8(flags), _u8(cmd), len(payload)]) + payload
    crc = crc16(body)
    return bytes([UF4_SOF1, UF4_SOF2]) + body + bytes([crc & 0xFF, crc >> 8])


def response_cmd_for(cmd: int) -> int:
    mapping = {
        Uf4Command.READ_REQ: Uf4Command.READ_RSP,
        Uf4Command.WRITE_REQ: Uf4Command.WRITE_RSP,
        Uf4Command.STREAM_START_REQ: Uf4Command.STREAM_START_RSP,
        Uf4Command.STREAM_STOP_REQ: Uf4Command.STREAM_STOP_RSP,
        Uf4Command.SAVE_REQ: Uf4Command.SAVE_RSP,
    }
    return int(mapping.get(_u8(cmd), _u8(cmd)))


def is_request_cmd(cmd: int) -> bool:
    return _u8(cmd) in {
        Uf4Command.READ_REQ,
        Uf4Command.WRITE_REQ,
        Uf4Command.STREAM_START_REQ,
        Uf4Command.STREAM_STOP_REQ,
        Uf4Command.SAVE_REQ,
    }


def encode_tv(id_: int | IntEnum, value: int | bytes | bytearray | memoryview | None = 0) -> bytes:
    if value is None or value == b"":
        encoded_value = 0
    elif isinstance(value, int):
        encoded_value = value
    else:
        raw = bytes(value)
        if len(raw) == 0:
            encoded_value = 0
        elif len(raw) == 1:
            encoded_value = raw[0]
        else:
            encoded_value = int.from_bytes(raw[:2], "big")
    return bytes([_u8(int(id_)), (_u16(encoded_value) >> 8) & 0xFF, _u16(encoded_value) & 0xFF])


def encode_tv_items(items: Iterable[tuple[int | IntEnum, int | bytes | None] | Uf4TvItem]) -> bytes:
    payload = bytearray()
    for item in items:
        if isinstance(item, Uf4TvItem):
            payload.extend(encode_tv(item.id, item.value))
        else:
            id_, value = item
            payload.extend(encode_tv(id_, value))
    return bytes(payload)


def iter_tv_items(data: bytes | bytearray | memoryview, strict: bool = True):
    payload = bytes(data or b"")
    remainder = len(payload) % UF4_TV_SIZE
    if strict and remainder:
        raise ValueError(f"UF4COM TV length must be a multiple of 3, got {len(payload)}")

    valid_len = len(payload) - remainder
    for offset in range(0, valid_len, UF4_TV_SIZE):
        raw = payload[offset:offset + UF4_TV_SIZE]
        id_ = raw[0]
        value = (raw[1] << 8) | raw[2]
        try:
            data_id = Uf4DataId(id_)
        except ValueError:
            data_id = None
        yield Uf4TvItem(id=id_, value=value, raw=raw, data_id=data_id)

    if not strict and remainder:
        raw = payload[valid_len:]
        yield Uf4TvItem(id=raw[0], value=None, raw=raw, data_id=None)


def build_error_frame(request: Uf4Frame, rsp_cmd: int, error: int | Uf4Error) -> bytes:
    return build_frame(
        rsp_cmd,
        request.seq,
        encode_tv(0xFF, int(error)),
        Uf4Flag.ACK_FRAME | Uf4Flag.ERROR,
    )


def parse_error_payload(data: bytes | bytearray | memoryview) -> Uf4Error | int | None:
    items = list(iter_tv_items(data, strict=False))
    if not items or items[0].id != 0xFF or items[0].value is None:
        return None
    try:
        return Uf4Error(items[0].value)
    except ValueError:
        return items[0].value


class Uf4FrameParser:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.state = Uf4ParserState.WAIT_SOF1
        self.seq = 0
        self.flags = 0
        self.cmd = 0
        self.expected_len = 0
        self.data = bytearray()
        self.crc_rx = 0

    def input_byte(self, byte: int) -> Uf4Frame | None:
        byte = _u8(byte)
        if self.state == Uf4ParserState.WAIT_SOF1:
            self.state = Uf4ParserState.WAIT_SOF2 if byte == UF4_SOF1 else Uf4ParserState.WAIT_SOF1
            return None
        if self.state == Uf4ParserState.WAIT_SOF2:
            self.state = (Uf4ParserState.WAIT_SEQ if byte == UF4_SOF2 else
                          Uf4ParserState.WAIT_SOF2 if byte == UF4_SOF1 else Uf4ParserState.WAIT_SOF1)
            return None
        if self.state == Uf4ParserState.WAIT_SEQ:
            self.seq = byte
            self.state = Uf4ParserState.WAIT_FLAGS
            return None
        if self.state == Uf4ParserState.WAIT_FLAGS:
            self.flags = byte
            self.state = Uf4ParserState.WAIT_CMD
            return None
        if self.state == Uf4ParserState.WAIT_CMD:
            self.cmd = byte
            self.state = Uf4ParserState.WAIT_LEN
            return None
        if self.state == Uf4ParserState.WAIT_LEN:
            self.expected_len = byte
            self.data.clear()
            self.state = Uf4ParserState.WAIT_CRC_L if byte == 0 else Uf4ParserState.WAIT_DATA
            return None
        if self.state == Uf4ParserState.WAIT_DATA:
            self.data.append(byte)
            if len(self.data) >= self.expected_len:
                self.state = Uf4ParserState.WAIT_CRC_L
            return None
        if self.state == Uf4ParserState.WAIT_CRC_L:
            self.crc_rx = byte
            self.state = Uf4ParserState.WAIT_CRC_H
            return None
        if self.state == Uf4ParserState.WAIT_CRC_H:
            self.crc_rx |= byte << 8
            frame = Uf4Frame(self.seq, self.flags, self.cmd, bytes(self.data))
            valid = frame_crc(frame) == self.crc_rx
            self.reset()
            return frame if valid else None
        self.reset()
        return None

    def feed(self, data: bytes | bytearray | memoryview) -> list[Uf4Frame]:
        frames: list[Uf4Frame] = []
        for byte in bytes(data or b""):
            frame = self.input_byte(byte)
            if frame is not None:
                frames.append(frame)
        return frames


class Uf4ComRuntime:
    def __init__(
        self,
        config: Uf4Config | None = None,
        tx: Callable[[bytes], None] | None = None,
        frame_rx: Callable[[Uf4Frame], None] | None = None,
        ack_event: Callable[[int, int, Uf4AckStatus], None] | None = None,
        write_apply: Callable[[], None] | None = None,
    ) -> None:
        self.config = config or Uf4Config()
        self.tx = tx
        self.frame_rx = frame_rx
        self.ack_event = ack_event
        self.write_apply = write_apply
        self.parser = Uf4FrameParser()
        self.now_ms = 0
        self._requests: list[_PendingRequest] = []
        self._registers: dict[int, Uf4Register] = {}
        self._stream_enable = False
        self._stream_ids: list[int] = []

    def send_frame(
        self,
        seq: int,
        flags: int,
        cmd: int,
        data: bytes | bytearray | memoryview | None = b"",
    ) -> bool:
        frame = build_frame(cmd, seq, data, flags)
        if self.tx is None:
            return False
        self.tx(frame)
        if flags & Uf4Flag.ACK_REQ and not flags & Uf4Flag.ACK_FRAME:
            return self._add_request(seq, response_cmd_for(cmd), frame)
        return True

    def input_byte(self, byte: int) -> int:
        frame = self.parser.input_byte(byte)
        if frame is None:
            return 0
        if frame.flags & Uf4Flag.ACK_FRAME:
            self._match_ack(frame)
            if self.frame_rx is not None:
                self.frame_rx(frame)
            return 1
        if is_request_cmd(frame.cmd):
            self._dispatch_request(frame)
        elif self.frame_rx is not None:
            self.frame_rx(frame)
        return 1

    def input_buffer(self, data: bytes | bytearray | memoryview) -> int:
        return sum(self.input_byte(byte) for byte in bytes(data or b""))

    def process(self) -> None:
        self.now_ms = (self.now_ms + 1) & 0xFFFFFFFF
        self.process_ms(self.now_ms)

    def process_ms(self, now_ms: int) -> None:
        self.now_ms = int(now_ms) & 0xFFFFFFFF
        for request in list(self._requests):
            if not request.active:
                continue
            if ((self.now_ms - request.last_tx_ms) & 0xFFFFFFFF) < request.timeout_ms:
                continue
            if request.retries_left <= 0:
                request.active = False
                self._notify_ack(request.seq, request.expected_cmd, Uf4AckStatus.TIMEOUT)
                continue
            if self.tx is not None:
                self.tx(request.frame)
            request.retries_left -= 1
            request.last_tx_ms = self.now_ms
        self._requests = [request for request in self._requests if request.active]
        self._stream_task()

    def bind_registers(self, registers: Iterable[Uf4Register | tuple[int, int, Uf4IdPermission | int]]) -> None:
        self._registers.clear()
        for item in registers:
            if isinstance(item, Uf4Register):
                register = item
            else:
                id_, value, permission = item
                register = Uf4Register(id=_u8(id_), value=_u16(value), permission=Uf4IdPermission(permission))
            self._registers[_u8(register.id)] = register

    def get_register(self, id_: int) -> Uf4Register | None:
        return self._registers.get(_u8(id_))

    def set_register_value(self, id_: int, value: int) -> None:
        register = self._registers.get(_u8(id_))
        if register is None:
            self._registers[_u8(id_)] = Uf4Register(_u8(id_), _u16(value), Uf4IdPermission.RW)
        else:
            register.value = _u16(value)

    def _add_request(self, seq: int, expected_cmd: int, frame: bytes) -> bool:
        if len(self._requests) >= UF4_MAX_PENDING_REQUESTS:
            self._notify_ack(seq, expected_cmd, Uf4AckStatus.DROPPED)
            return False
        timeout = self.config.ack_timeout_ms or UF4_DEFAULT_ACK_TIMEOUT_MS
        self._requests.append(
            _PendingRequest(
                seq=_u8(seq),
                expected_cmd=_u8(expected_cmd),
                frame=bytes(frame),
                retries_left=max(0, int(self.config.ack_retries)),
                last_tx_ms=self.now_ms,
                timeout_ms=max(1, int(timeout)),
            )
        )
        return True

    def _match_ack(self, frame: Uf4Frame) -> bool:
        for request in self._requests:
            if (
                request.active
                and request.seq == frame.seq
                and request.expected_cmd == frame.cmd
            ):
                request.active = False
                self._notify_ack(frame.seq, frame.cmd, Uf4AckStatus.DONE)
                return True
        return False

    def _notify_ack(self, seq: int, cmd: int, status: Uf4AckStatus) -> None:
        if self.ack_event is not None:
            self.ack_event(_u8(seq), _u8(cmd), status)

    def _should_reply(self, frame: Uf4Frame) -> bool:
        return bool(frame.flags & Uf4Flag.ACK_REQ)

    def _send_response(self, request: Uf4Frame, flags: int, cmd: int, data: bytes = b"") -> None:
        if self.tx is not None:
            self.tx(build_frame(cmd, request.seq, data, flags))

    def _send_error(self, request: Uf4Frame, rsp_cmd: int, error: Uf4Error) -> None:
        if self._should_reply(request):
            self._send_response(
                request,
                Uf4Flag.ACK_FRAME | Uf4Flag.ERROR,
                rsp_cmd,
                encode_tv(0xFF, error),
            )

    def _dispatch_request(self, frame: Uf4Frame) -> None:
        if frame.cmd == Uf4Command.READ_REQ:
            self._handle_read(frame)
        elif frame.cmd == Uf4Command.WRITE_REQ:
            self._handle_write(frame)
        elif frame.cmd == Uf4Command.STREAM_START_REQ:
            self._handle_stream_start(frame)
        elif frame.cmd == Uf4Command.STREAM_STOP_REQ:
            self._handle_stream_stop(frame)
        elif frame.cmd == Uf4Command.SAVE_REQ:
            self._handle_save(frame)
        else:
            self._send_error(frame, frame.cmd, Uf4Error.INVALID_CMD)

    def _handle_read(self, frame: Uf4Frame) -> None:
        if len(frame.data) % UF4_TV_SIZE:
            self._send_error(frame, Uf4Command.READ_RSP, Uf4Error.INVALID_LEN)
            return
        response = bytearray()
        for item in iter_tv_items(frame.data):
            register = self.get_register(item.id)
            if register is None:
                self._send_error(frame, Uf4Command.READ_RSP, Uf4Error.INVALID_ID)
                return
            response.extend(encode_tv(register.id, register.value))
        if self._should_reply(frame):
            self._send_response(frame, Uf4Flag.ACK_FRAME, Uf4Command.READ_RSP, bytes(response))

    def _handle_write(self, frame: Uf4Frame) -> None:
        if len(frame.data) % UF4_TV_SIZE:
            self._send_error(frame, Uf4Command.WRITE_RSP, Uf4Error.INVALID_LEN)
            return
        for item in iter_tv_items(frame.data):
            register = self.get_register(item.id)
            if register is None:
                self._send_error(frame, Uf4Command.WRITE_RSP, Uf4Error.INVALID_ID)
                return
            if register.permission == Uf4IdPermission.RO:
                self._send_error(frame, Uf4Command.WRITE_RSP, Uf4Error.WRITE_PROTECT)
                return
            register.value = _u16(item.value or 0)
        if self.write_apply is not None:
            self.write_apply()
        if self._should_reply(frame):
            self._send_response(frame, Uf4Flag.ACK_FRAME, Uf4Command.WRITE_RSP, frame.data)

    def _handle_stream_start(self, frame: Uf4Frame) -> None:
        if len(frame.data) % UF4_TV_SIZE:
            self._send_error(frame, Uf4Command.STREAM_START_RSP, Uf4Error.INVALID_LEN)
            return
        ids = [item.id for item in iter_tv_items(frame.data)] if frame.data else list(self._registers)
        if len(ids) > UF4_MAX_DATA_LEN // UF4_TV_SIZE:
            self._send_error(frame, Uf4Command.STREAM_START_RSP, Uf4Error.INVALID_LEN)
            return
        for id_ in ids:
            if self.get_register(id_) is None:
                self._stream_enable = False
                self._stream_ids = []
                self._send_error(frame, Uf4Command.STREAM_START_RSP, Uf4Error.INVALID_ID)
                return
        self._stream_enable = True
        self._stream_ids = ids
        if self._should_reply(frame):
            self._send_response(frame, Uf4Flag.ACK_FRAME, Uf4Command.STREAM_START_RSP)

    def _handle_stream_stop(self, frame: Uf4Frame) -> None:
        self._stream_enable = False
        self._stream_ids = []
        if self._should_reply(frame):
            self._send_response(frame, Uf4Flag.ACK_FRAME, Uf4Command.STREAM_STOP_RSP)

    def _handle_save(self, frame: Uf4Frame) -> None:
        if frame.data:
            self._send_error(frame, Uf4Command.SAVE_RSP, Uf4Error.INVALID_LEN)
            return
        if self._should_reply(frame):
            self._send_response(frame, Uf4Flag.ACK_FRAME, Uf4Command.SAVE_RSP)

    def _stream_task(self) -> None:
        if not self._stream_enable or self.tx is None:
            return
        payload = bytearray()
        for id_ in self._stream_ids:
            register = self.get_register(id_)
            if register is None or len(payload) + UF4_TV_SIZE > UF4_MAX_DATA_LEN:
                continue
            payload.extend(encode_tv(register.id, register.value))
        self.tx(build_frame(Uf4Command.STREAM_DATA, 0, bytes(payload)))


__all__ = [
    "UF4_SOF1",
    "UF4_SOF2",
    "UF4_MAX_DATA_LEN",
    "UF4_V5_HEADER_LEN",
    "UF4_CRC_LEN",
    "UF4_MAX_FRAME_LEN",
    "UF4_DEFAULT_ACK_TIMEOUT_MS",
    "UF4_DEFAULT_ACK_RETRIES",
    "UF4_MAX_PENDING_REQUESTS",
    "UF4_TV_SIZE",
    "Uf4Command",
    "Uf4Flag",
    "Uf4DataId",
    "Uf4Error",
    "Uf4AckStatus",
    "Uf4IdPermission",
    "Uf4Frame",
    "Uf4TvItem",
    "Uf4Config",
    "Uf4Register",
    "Uf4FrameParser",
    "Uf4ComRuntime",
    "crc16",
    "frame_crc",
    "build_frame",
    "build_error_frame",
    "response_cmd_for",
    "is_request_cmd",
    "encode_tv",
    "encode_tv_items",
    "iter_tv_items",
    "parse_error_payload",
]
