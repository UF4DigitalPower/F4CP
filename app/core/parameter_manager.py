# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


PARAM_MAGIC = 0x55463450
PARAM_VERSION = 1
PARAM_ACCESS_RO = "RO"
PARAM_ACCESS_RW = "RW"


@dataclass(frozen=True)
class ParameterSpec:
    group: str
    name: str
    uf4_id: str
    access: str
    default: int
    unit: str
    minimum: int
    maximum: int
    note: str
    persistent: bool = False

    @property
    def id_value(self) -> int:
        return int(self.uf4_id, 16)

    @property
    def writable(self) -> bool:
        return self.access == PARAM_ACCESS_RW


@dataclass(frozen=True)
class ParameterEntry:
    spec: ParameterSpec
    value: int
    saved: int

    @property
    def dirty(self) -> bool:
        return self.value != self.saved


class ParameterError(ValueError):
    pass


class ParameterNotFoundError(ParameterError):
    pass


class ParameterPermissionError(ParameterError):
    pass


class ParameterRangeError(ParameterError):
    pass


PARAMETER_SPECS = (
    # ParameterSpec("实时遥测", "输入电压", "0x0A", "RO", 0, "mV", 0, 65535, "UF4_ID_INPUT_VOLTAGE"),
    # ParameterSpec("实时遥测", "输入电流", "0x0B", "RO", 0, "mA", 0, 65535, "UF4_ID_INPUT_CURRENT"),
    # ParameterSpec("实时遥测", "输出电压", "0x0C", "RO", 0, "mV", 0, 65535, "UF4_ID_OUTPUT_VOLTAGE"),
    # ParameterSpec("实时遥测", "输出电流", "0x0D", "RO", 0, "mA", 0, 65535, "UF4_ID_OUTPUT_CURRENT"),
    # ParameterSpec("实时遥测", "通道温度1", "0x0E", "RO", 0, "deg C", 0, 65535, "UF4_ID_CORE_TEMPERATURE"),
    # ParameterSpec("实时遥测", "温度 1", "0x0F", "RO", 0, "deg C", 0, 65535, "UF4_ID_TEMP1_TEMPERATURE"),
    # ParameterSpec("实时遥测", "温度 2", "0x10", "RO", 0, "deg C", 0, 65535, "UF4_ID_TEMP2_TEMPERATURE"),
    # ParameterSpec("状态只读", "CC/CV 模式", "0x14", "RO", 0, "enum", 0, 65535, "UF4_ID_CC_CV_MODE"),
    # ParameterSpec("状态只读", "故障状态", "0x16", "RO", 0, "bits", 0, 65535, "UF4_ID_FAULT_STATE"),
    # ParameterSpec("状态只读", "状态机标志位", "0x17", "RO", 0, "bits", 0, 65535, "UF4_ID_STATE_MACHINE_FLAG_BITS"),
    # ParameterSpec("状态只读", "状态机状态", "0x18", "RO", 0, "enum", 0, 65535, "UF4_ID_STATE_MACHINE_STATE"),
    # ParameterSpec("原始与环路", "输入电压原始值", "0x19", "RO", 0, "raw", 0, 65535, "UF4_ID_INPUT_VOLTAGE_RAW"),
    # ParameterSpec("原始与环路", "输入电流原始值", "0x1A", "RO", 0, "raw", 0, 65535, "UF4_ID_INPUT_CURRENT_RAW"),
    # ParameterSpec("原始与环路", "输出电压原始值", "0x1B", "RO", 0, "raw", 0, 65535, "UF4_ID_OUTPUT_VOLTAGE_RAW"),
    # ParameterSpec("原始与环路", "输出电流原始值", "0x1C", "RO", 0, "raw", 0, 65535, "UF4_ID_OUTPUT_CURRENT_RAW"),
    ParameterSpec("原始与环路", "OTP 当前值", "0x1D", "RO", 0, "deg C", 0, 65535, "UF4_ID_OTP_VALUE"),
    ParameterSpec("原始与环路", "OVP 当前值", "0x1F", "RO", 0, "mV", 0, 65535, "UF4_ID_OVP_VALUE"),
    ParameterSpec("原始与环路", "OCP 当前值", "0x21", "RO", 0, "mA", 0, 65535, "UF4_ID_OCP_VALUE"),
    ParameterSpec("原始与环路", "占空比指令", "0x23", "RO", 0, "raw", 0, 65535, "UF4_ID_DUTY_CMD"),
    ParameterSpec("原始与环路", "PWM A 比较值", "0x24", "RO", 0, "raw", 0, 65535, "UF4_ID_PWM_A_COMPARE"),
    ParameterSpec("原始与环路", "PWM D 比较值", "0x25", "RO", 0, "raw", 0, 65535, "UF4_ID_PWM_D_COMPARE"),
    ParameterSpec("原始与环路", "风扇转速", "0x26", "RO", 0, "rpm", 0, 65535, "UF4_ID_FAN_SPEED"),
    ParameterSpec("原始与环路", "电流环反馈", "0x29", "RO", 0, "raw", 0, 65535, "UF4_ID_LOOP_CURRENT_FEEDBACK"),
    ParameterSpec("原始与环路", "电流环参考", "0x2A", "RO", 0, "raw", 0, 65535, "UF4_ID_LOOP_CURRENT_REFERENCE"),
    ParameterSpec("原始与环路", "电压环电流参考", "0x2B", "RO", 0, "raw", 0, 65535, "UF4_ID_VOLTAGE_LOOP_CURRENT_REFERENCE"),

    ParameterSpec("运行设定", "设定电压上限", "0x11", "RW", 0, "mV", 0, 65535, "UF4_ID_SET_VOLTAGE_LIMIT", True),
    ParameterSpec("运行设定", "设定电流上限", "0x12", "RW", 0, "mA", 0, 65535, "UF4_ID_SET_CURRENT_LIMIT", True),
    ParameterSpec("运行设定", "电源开关状态", "0x15", "RW", 0, "enum", 0, 65535, "UF4_ID_POWER_STATE"),
    ParameterSpec("运行设定", "风扇设定值", "0x27", "RW", 0, "raw", 0, 65535, "UF4_ID_FAN_SET_VALUE"),
    ParameterSpec("保护阈值", "OTP 设定值", "0x1E", "RW", 0, "deg C", 0, 65535, "UF4_ID_OTP_SET_VALUE"),
    ParameterSpec("保护阈值", "OVP 设定值", "0x20", "RW", 0, "mV", 0, 65535, "UF4_ID_OVP_SET_VALUE"),
    ParameterSpec("保护阈值", "输出过流保护", "0x22", "RW", 10000, "mA", 0, 65535, "UF4_ID_OCP_SET_VALUE", True),
    ParameterSpec("保护阈值", "输入过压保护", "0x30", "RW", 60000, "mV", 0, 65535, "UF4_ID_CFG_VIN_OVP", True),
    ParameterSpec("保护阈值", "输入欠压保护", "0x31", "RW", 9000, "mV", 0, 65535, "UF4_ID_CFG_VIN_UVP", True),
    ParameterSpec("保护阈值", "输出过压保护", "0x32", "RW", 30000, "mV", 0, 65535, "UF4_ID_CFG_VOUT_OVP", True),
    ParameterSpec("硬件换算", "ADC 参考电压", "0x33", "RW", 3300, "mV", 0, 65535, "UF4_ID_CFG_ADC_VREF", True),
    ParameterSpec("硬件换算", "输入分压上电阻", "0x34", "RW", 750, "x100 ohm", 1, 65535, "UF4_ID_CFG_VIN_R_UPPER", True),
    ParameterSpec("硬件换算", "输入分压下电阻", "0x35", "RW", 50, "x100 ohm", 1, 65535, "UF4_ID_CFG_VIN_R_LOWER", True),
    ParameterSpec("硬件换算", "输出分压上电阻", "0x36", "RW", 750, "x100 ohm", 1, 65535, "UF4_ID_CFG_VOUT_R_UPPER", True),
    ParameterSpec("硬件换算", "输出分压下电阻", "0x37", "RW", 50, "x100 ohm", 1, 65535, "UF4_ID_CFG_VOUT_R_LOWER", True),
    ParameterSpec("硬件换算", "输入采样电阻", "0x38", "RW", 1000, "x10 uOhm", 1, 65535, "UF4_ID_CFG_SHUNT_IN", True),
    ParameterSpec("硬件换算", "输出采样电阻", "0x39", "RW", 1000, "x10 uOhm", 1, 65535, "UF4_ID_CFG_SHUNT_OUT", True),
    ParameterSpec("硬件换算", "输入电流放大倍数", "0x3A", "RW", 1000, "milli", 1, 65535, "UF4_ID_CFG_GAIN_IN", True),
    ParameterSpec("硬件换算", "输出电流放大倍数", "0x3B", "RW", 1000, "milli", 1, 65535, "UF4_ID_CFG_GAIN_OUT", True),
    ParameterSpec("校准", "电流零点偏移", "0x3C", "RW", 0, "int16 raw", 0, 65535, "UF4_ID_CFG_CURRENT_OFFSET", True),
    ParameterSpec("校准", "输入电压增益", "0x3D", "RW", 1000, "milli", 0, 65535, "UF4_ID_CFG_VIN_GAIN", True),
    ParameterSpec("校准", "输入电压偏移", "0x3E", "RW", 0, "int16 mV", 0, 65535, "UF4_ID_CFG_VIN_OFFSET", True),
    ParameterSpec("校准", "输出电压增益", "0x3F", "RW", 1000, "milli", 0, 65535, "UF4_ID_CFG_VOUT_GAIN", True),
    ParameterSpec("校准", "输出电压偏移", "0x40", "RW", 0, "int16 mV", 0, 65535, "UF4_ID_CFG_VOUT_OFFSET", True),
    ParameterSpec("校准", "输入电流增益", "0x41", "RW", 1000, "milli", 0, 65535, "UF4_ID_CFG_IIN_GAIN", True),
    ParameterSpec("校准", "输入电流偏移", "0x42", "RW", 0, "int16 mA", 0, 65535, "UF4_ID_CFG_IIN_OFFSET", True),
    ParameterSpec("校准", "输出电流增益", "0x43", "RW", 1000, "milli", 0, 65535, "UF4_ID_CFG_IOUT_GAIN", True),
    ParameterSpec("校准", "输出电流偏移", "0x44", "RW", 0, "int16 mA", 0, 65535, "UF4_ID_CFG_IOUT_OFFSET", True),
    ParameterSpec("PID", "电压环 KP", "0x45", "RW", 0, "1/10000", 0, 65535, "UF4_ID_CFG_VOLTAGE_KP", True),
    ParameterSpec("PID", "电压环 KI", "0x46", "RW", 0, "1/10000", 0, 65535, "UF4_ID_CFG_VOLTAGE_KI", True),
    ParameterSpec("PID", "电压环 KD", "0x47", "RW", 0, "1/10000", 0, 65535, "UF4_ID_CFG_VOLTAGE_KD", True),
    ParameterSpec("PID", "电流环 KP", "0x48", "RW", 0, "1/10000", 0, 65535, "UF4_ID_CFG_CURRENT_KP", True),
    ParameterSpec("PID", "电流环 KI", "0x49", "RW", 0, "1/10000", 0, 65535, "UF4_ID_CFG_CURRENT_KI", True),
    ParameterSpec("PID", "电流环 KD", "0x4A", "RW", 0, "1/10000", 0, 65535, "UF4_ID_CFG_CURRENT_KD", True),
)


def default_parameter_store_path() -> Path:
    return Path(__file__).resolve().parents[2] / "src" / "config" / "parameters.json"


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def as_signed16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def from_signed16(value: int) -> int:
    return value & 0xFFFF


class ParameterManager:
    def __init__(
        self,
        specs: Iterable[ParameterSpec] = PARAMETER_SPECS,
        storage_path: str | Path | None = None,
        *,
        load: bool = True,
    ):
        self.specs = tuple(specs)
        self.storage_path = Path(storage_path) if storage_path is not None else default_parameter_store_path()
        self._values = {spec.note: int(spec.default) for spec in self.specs}
        self._saved = dict(self._values)
        self._by_note = {spec.note: spec for spec in self.specs}
        self._by_id = {spec.id_value: spec for spec in self.specs}
        if load:
            self.load()

    @property
    def count(self) -> int:
        return len(self.specs)

    @property
    def dirty(self) -> bool:
        return any(self._values[key] != self._saved[key] for key in self._values)

    @property
    def persistent_count(self) -> int:
        return sum(1 for spec in self.specs if spec.persistent)

    def spec(self, key: str | int) -> ParameterSpec:
        if isinstance(key, int):
            found = self._by_id.get(key)
            if found is None:
                raise ParameterNotFoundError(f"Unknown parameter id 0x{key:02X}")
            return found
        if key in self._by_note:
            return self._by_note[key]
        try:
            numeric_id = int(key, 16)
        except ValueError:
            numeric_id = -1
        if numeric_id in self._by_id:
            return self._by_id[numeric_id]
        raise ParameterNotFoundError(f"Unknown parameter {key!r}")

    def entry(self, key: str | int) -> ParameterEntry:
        spec = self.spec(key)
        return ParameterEntry(spec, self._values[spec.note], self._saved[spec.note])

    def read(self, key: str | int) -> int:
        spec = self.spec(key)
        return self._values[spec.note]

    def update_readonly(self, key: str | int, value: int) -> None:
        spec = self.spec(key)
        self._values[spec.note] = self._checked_value(spec, value)
        self._saved[spec.note] = self._values[spec.note]

    def write(self, key: str | int, value: int) -> None:
        spec = self.spec(key)
        if not spec.writable:
            raise ParameterPermissionError(f"{spec.note} is read only")
        self._values[spec.note] = self._checked_value(spec, value)

    def write_many(self, values: dict[str | int, int]) -> None:
        for key, value in values.items():
            self.write(key, value)

    def reset_defaults(self, *, writable_only: bool = True) -> None:
        for spec in self.specs:
            if writable_only and not spec.writable:
                continue
            self._values[spec.note] = spec.default

    def mark_saved(self, keys: Iterable[str | int] | None = None) -> None:
        if keys is None:
            self._saved = dict(self._values)
            return
        for key in keys:
            spec = self.spec(key)
            self._saved[spec.note] = self._values[spec.note]

    def dirty_entries(self) -> list[ParameterEntry]:
        return [self.entry(spec.note) for spec in self.specs if self._values[spec.note] != self._saved[spec.note]]

    def writable_values(self, *, dirty_only: bool = False, persistent_only: bool = False) -> dict[str, int]:
        result: dict[str, int] = {}
        for spec in self.specs:
            if not spec.writable:
                continue
            if persistent_only and not spec.persistent:
                continue
            if dirty_only and self._values[spec.note] == self._saved[spec.note]:
                continue
            result[spec.note] = self._values[spec.note]
        return result

    def protocol_pairs(self, *, dirty_only: bool = False, persistent_only: bool = False) -> list[tuple[int, int]]:
        return [
            (self.spec(note).id_value, value)
            for note, value in self.writable_values(
                dirty_only=dirty_only,
                persistent_only=persistent_only,
            ).items()
        ]

    def load(self) -> bool:
        if not self.storage_path.exists():
            return False
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if payload.get("magic") != PARAM_MAGIC or payload.get("version") != PARAM_VERSION:
            return False

        loaded = False
        for record in payload.get("records", []):
            if not self._record_valid(record):
                continue
            try:
                spec = self.spec(int(record["id"]))
            except ParameterNotFoundError:
                continue
            if not spec.writable:
                continue
            value = self._checked_value(spec, int(record["value"]))
            self._values[spec.note] = value
            self._saved[spec.note] = value
            loaded = True
        return loaded

    def save(self, *, persistent_only: bool = True) -> None:
        records = []
        saved_keys = []
        for spec in self.specs:
            if not spec.writable:
                continue
            if persistent_only and not spec.persistent:
                continue
            value = self._checked_value(spec, self._values[spec.note])
            records.append(self._make_record(spec, value))
            saved_keys.append(spec.note)
        payload = {
            "magic": PARAM_MAGIC,
            "version": PARAM_VERSION,
            "records": records,
        }
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.mark_saved(saved_keys)

    def _checked_value(self, spec: ParameterSpec, value: int) -> int:
        value = int(value)
        if value < spec.minimum or value > spec.maximum:
            raise ParameterRangeError(
                f"{spec.note} value {value} out of range {spec.minimum}..{spec.maximum}"
            )
        return value

    def _make_record(self, spec: ParameterSpec, value: int) -> dict[str, int | str]:
        record = {
            "id": spec.id_value,
            "note": spec.note,
            "value": value,
        }
        crc_data = f"{record['id']}:{record['value']}".encode("ascii")
        record["crc"] = crc16_ccitt(crc_data)
        return record

    def _record_valid(self, record: dict) -> bool:
        try:
            expected = crc16_ccitt(f"{int(record['id'])}:{int(record['value'])}".encode("ascii"))
            return int(record.get("crc", -1)) == expected
        except (KeyError, TypeError, ValueError):
            return False
