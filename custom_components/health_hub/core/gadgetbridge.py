"""What Health Hub reads from Gadgetbridge's database, and how it cleans each row.

This module is the only place that knows Gadgetbridge's internal table layout.
When a Gadgetbridge update changes that layout, this is the file to adjust; the
phone app is deliberately generic and just sends the columns asked for here.

Pure Python: no Home Assistant imports, so it can be tested on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Seconds vs milliseconds: Gadgetbridge's per-minute activity samples use epoch
# seconds; its other "time samples" use epoch milliseconds.
UNIT_S = "s"
UNIT_MS = "ms"


@dataclass(frozen=True)
class TableSpec:
    """One Gadgetbridge table the phone app should send."""

    name: str
    ts_column: str
    ts_unit: str
    columns: tuple[str, ...]
    kind: str  # which normaliser handles the rows (see normalise_row)


# Columns are listed explicitly so personal fields (names, birthdays, locations,
# file paths) are never sent off the phone.
TABLES: tuple[TableSpec, ...] = (
    TableSpec(
        name="XIAOMI_ACTIVITY_SAMPLE",
        ts_column="TIMESTAMP",
        ts_unit=UNIT_S,
        columns=(
            "TIMESTAMP",
            "DEVICE_ID",
            "RAW_INTENSITY",
            "STEPS",
            "RAW_KIND",
            "HEART_RATE",
            "STRESS",
            "SPO2",
            "DISTANCE_CM",
            "ACTIVE_CALORIES",
        ),
        kind="minute",
    ),
    TableSpec(
        name="XIAOMI_DAILY_SUMMARY_SAMPLE",
        ts_column="TIMESTAMP",
        ts_unit=UNIT_MS,
        columns=(
            "TIMESTAMP",
            "DEVICE_ID",
            "TIMEZONE",
            "STEPS",
            "HR_RESTING",
            "HR_MAX",
            "HR_MIN",
            "HR_AVG",
            "STRESS_AVG",
            "STRESS_MAX",
            "STRESS_MIN",
            "STANDING",
            "CALORIES",
            "ACTIVE_CALORIES",
            "SPO2_MAX",
            "SPO2_MIN",
            "SPO2_AVG",
            "TRAINING_LOAD_DAY",
            "TRAINING_LOAD_WEEK",
            "VITALITY_CURRENT",
            "RECOVERY_HOURS",
        ),
        kind="daily",
    ),
    TableSpec(
        name="XIAOMI_SLEEP_TIME_SAMPLE",
        ts_column="TIMESTAMP",
        ts_unit=UNIT_MS,
        columns=(
            "TIMESTAMP",
            "DEVICE_ID",
            "WAKEUP_TIME",
            "IS_AWAKE",
            "TOTAL_DURATION",
            "DEEP_SLEEP_DURATION",
            "LIGHT_SLEEP_DURATION",
            "REM_SLEEP_DURATION",
            "AWAKE_DURATION",
        ),
        kind="sleep_session",
    ),
    TableSpec(
        name="XIAOMI_SLEEP_STAGE_SAMPLE",
        ts_column="TIMESTAMP",
        ts_unit=UNIT_MS,
        columns=("TIMESTAMP", "DEVICE_ID", "STAGE"),
        kind="sleep_stage",
    ),
    TableSpec(
        name="XIAOMI_MANUAL_SAMPLE",
        ts_column="TIMESTAMP",
        ts_unit=UNIT_MS,
        columns=("TIMESTAMP", "DEVICE_ID", "TYPE", "VALUE"),
        kind="manual",
    ),
    TableSpec(
        name="BATTERY_LEVEL",
        ts_column="TIMESTAMP",
        ts_unit=UNIT_S,  # confirmed from a real export (26 Oct 2026)
        columns=("TIMESTAMP", "DEVICE_ID", "LEVEL", "BATTERY_INDEX"),
        kind="battery",
    ),
    TableSpec(
        name="BASE_ACTIVITY_SUMMARY",
        ts_column="START_TIME",
        ts_unit=UNIT_MS,
        # No location, GPX path, photos or raw blobs.
        columns=(
            "_id",
            "NAME",
            "START_TIME",
            "END_TIME",
            "ACTIVITY_KIND",
            "DEVICE_ID",
            "SUMMARY_DATA",
        ),
        kind="workout",
    ),
)

TABLES_BY_NAME: dict[str, TableSpec] = {t.name: t for t in TABLES}

# The DEVICE table is small and sent whole on every sync, without the
# Bluetooth address.
DEVICE_TABLE = "DEVICE"
DEVICE_COLUMNS = ("_id", "NAME", "MANUFACTURER", "TYPE_NAME", "MODEL", "ALIAS")


_MS_THRESHOLD = 10**11  # epoch seconds stay below this until the year 5138


def to_seconds(value: Any, unit: str) -> int | None:
    """Convert a Gadgetbridge timestamp to epoch seconds.

    The unit is checked against the value's size, so a table whose unit was
    guessed wrong still gives correct times.
    """
    if value is None:
        return None
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    if value >= _MS_THRESHOLD:
        return value // 1000
    return value


def from_seconds(value: int, unit: str) -> int:
    """Convert epoch seconds to a Gadgetbridge timestamp in the table's unit."""
    return value * 1000 if unit == UNIT_MS else value


def _int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _in_range(value: Any, low: int, high: int) -> int | None:
    """Keep a reading only if it is inside a plausible range.

    Gadgetbridge stores "no reading" as 0 (and sometimes 255 or -1), so anything
    outside the range is treated as missing rather than as a value.
    """
    value = _int(value)
    if value is None or value < low or value > high:
        return None
    return value


def _non_negative(value: Any) -> int:
    value = _int(value)
    return value if value is not None and value > 0 else 0


def normalise_row(spec: TableSpec, row: dict[str, Any]) -> dict[str, Any] | None:
    """Turn one raw Gadgetbridge row into Health Hub's own shape.

    Returns None for rows that cannot be used (for example, no timestamp).
    """
    ts = to_seconds(row.get(spec.ts_column), spec.ts_unit)
    if ts is None:
        return None
    device_id = _int(row.get("DEVICE_ID")) or 0

    if spec.kind == "minute":
        return {
            "device_id": device_id,
            "ts": ts,
            "steps": _non_negative(row.get("STEPS")),
            "heart_rate": _in_range(row.get("HEART_RATE"), 25, 240),
            "stress": _in_range(row.get("STRESS"), 1, 100),
            "spo2": _in_range(row.get("SPO2"), 70, 100),
            "distance_cm": _non_negative(row.get("DISTANCE_CM")),
            "active_calories": _non_negative(row.get("ACTIVE_CALORIES")),
            "raw_kind": _int(row.get("RAW_KIND")),
            "raw_intensity": _int(row.get("RAW_INTENSITY")),
        }

    if spec.kind == "daily":
        # TIMEZONE is in 15-minute steps (44 = UTC+11:00).
        tz_quarters = _int(row.get("TIMEZONE"))
        return {
            "device_id": device_id,
            "ts": ts,
            "tz_offset_min": tz_quarters * 15 if tz_quarters is not None else None,
            "steps": _int(row.get("STEPS")),
            "hr_resting": _in_range(row.get("HR_RESTING"), 25, 200),
            "hr_min": _in_range(row.get("HR_MIN"), 25, 240),
            "hr_max": _in_range(row.get("HR_MAX"), 25, 240),
            "hr_avg": _in_range(row.get("HR_AVG"), 25, 240),
            "stress_avg": _in_range(row.get("STRESS_AVG"), 1, 100),
            "stress_min": _in_range(row.get("STRESS_MIN"), 1, 100),
            "stress_max": _in_range(row.get("STRESS_MAX"), 1, 100),
            "spo2_avg": _in_range(row.get("SPO2_AVG"), 70, 100),
            "spo2_min": _in_range(row.get("SPO2_MIN"), 70, 100),
            "spo2_max": _in_range(row.get("SPO2_MAX"), 70, 100),
            "standing": _int(row.get("STANDING")),
            "calories": _int(row.get("CALORIES")),
            "active_calories": _int(row.get("ACTIVE_CALORIES")),
            "training_load_day": _int(row.get("TRAINING_LOAD_DAY")),
            "training_load_week": _int(row.get("TRAINING_LOAD_WEEK")),
            "vitality": _int(row.get("VITALITY_CURRENT")),
            "recovery_hours": _int(row.get("RECOVERY_HOURS")),
        }

    if spec.kind == "sleep_session":
        return {
            "device_id": device_id,
            "ts": ts,
            "wakeup_ts": to_seconds(row.get("WAKEUP_TIME"), spec.ts_unit),
            "is_awake": _int(row.get("IS_AWAKE")),
            "total_min": _int(row.get("TOTAL_DURATION")),
            "deep_min": _int(row.get("DEEP_SLEEP_DURATION")),
            "light_min": _int(row.get("LIGHT_SLEEP_DURATION")),
            "rem_min": _int(row.get("REM_SLEEP_DURATION")),
            "awake_min": _int(row.get("AWAKE_DURATION")),
        }

    if spec.kind == "sleep_stage":
        return {"device_id": device_id, "ts": ts, "stage": _int(row.get("STAGE"))}

    if spec.kind == "manual":
        return {
            "device_id": device_id,
            "ts": ts,
            "type": _int(row.get("TYPE")),
            "value": _int(row.get("VALUE")),
        }

    if spec.kind == "battery":
        level = _in_range(row.get("LEVEL"), 0, 100)
        if level is None:
            return None
        return {
            "device_id": device_id,
            "ts": ts,
            "level": level,
            "battery_index": _int(row.get("BATTERY_INDEX")) or 0,
        }

    if spec.kind == "workout":
        workout_id = _int(row.get("_id"))
        if workout_id is None:
            return None
        return {
            "device_id": device_id,
            "workout_id": workout_id,
            "ts": ts,
            "end_ts": to_seconds(row.get("END_TIME"), spec.ts_unit),
            "kind": _int(row.get("ACTIVITY_KIND")),
            "name": row.get("NAME"),
            "summary_json": row.get("SUMMARY_DATA"),
        }

    return None


def normalise_device(row: dict[str, Any]) -> dict[str, Any] | None:
    device_id = _int(row.get("_id"))
    if device_id is None:
        return None
    return {
        "device_id": device_id,
        "name": row.get("ALIAS") or row.get("NAME"),
        "manufacturer": row.get("MANUFACTURER"),
        "type_name": row.get("TYPE_NAME"),
        "model": row.get("MODEL"),
    }
