"""Read history files made by tools/fitbit_takeout.py (or any other source
written in the same format).

Pure Python: no Home Assistant imports.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

FORMAT = "health_hub_history"
VERSION = 1

HOURLY_COLUMNS = (
    "hour_ts", "steps", "distance_m", "active_calories",
    "hr_mean", "hr_min", "hr_max", "hr_n",
    "spo2_mean", "spo2_min", "spo2_max", "spo2_n",
)
SLEEP_COLUMNS = (
    "start_ts", "end_ts", "total_min", "deep_min", "light_min", "rem_min", "awake_min", "score",
)
DAILY_METRICS = {"resting_heart_rate", "hrv", "respiratory_rate"}
MEASUREMENT_METRICS = {"weight"}
MAX_BYTES = 200 * 1024 * 1024  # uncompressed


class HistoryError(ValueError):
    """The file is not a history file Health Hub can import."""


@dataclass
class History:
    source: str
    hourly: list[dict[str, Any]] = field(default_factory=list)
    daily: list[tuple[str, str, float]] = field(default_factory=list)  # metric, YYYY-MM-DD, value
    measurements: list[tuple[str, int, float]] = field(default_factory=list)  # metric, ts, value
    sleep: list[dict[str, Any]] = field(default_factory=list)


def _section(data: dict, name: str, columns: tuple[str, ...] | None) -> list[list[Any]]:
    section = data.get(name) or {"columns": list(columns or ()), "rows": []}
    if not isinstance(section, dict) or not isinstance(section.get("rows"), list):
        raise HistoryError(f"'{name}' is malformed")
    if columns is not None and tuple(section.get("columns", ())) != columns:
        raise HistoryError(f"'{name}' has unexpected columns")
    for row in section["rows"]:
        if not isinstance(row, list):
            raise HistoryError(f"'{name}' has a malformed row")
    return section["rows"]


def _num(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoryError(f"expected a number, got {value!r}")
    return value


def parse_history(data: Any) -> History:
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise HistoryError("not a Health Hub history file")
    if data.get("version") != VERSION:
        raise HistoryError(f"unsupported history file version {data.get('version')!r}")
    source = str(data.get("source") or "import")
    if source == "band":
        raise HistoryError("'band' is reserved for data from the phone app")
    history = History(source=source)

    for row in _section(data, "hourly", HOURLY_COLUMNS):
        if len(row) != len(HOURLY_COLUMNS):
            raise HistoryError("'hourly' row has the wrong length")
        item = {c: _num(v) for c, v in zip(HOURLY_COLUMNS, row)}
        if item["hour_ts"] is None or int(item["hour_ts"]) % 3600:
            raise HistoryError("'hourly' timestamps must be on the hour")
        item["hour_ts"] = int(item["hour_ts"])
        history.hourly.append(item)

    for row in _section(data, "daily", ("metric", "date", "value")):
        metric, day, value = (row + [None, None, None])[:3]
        if metric not in DAILY_METRICS:
            continue  # newer files may carry more; skip what we don't chart
        try:
            date.fromisoformat(day)
        except (TypeError, ValueError) as err:
            raise HistoryError(f"bad date {day!r}") from err
        if _num(value) is not None:
            history.daily.append((metric, day, float(value)))

    for row in _section(data, "measurements", ("metric", "ts", "value")):
        metric, ts, value = (row + [None, None, None])[:3]
        if metric in MEASUREMENT_METRICS and _num(ts) is not None and _num(value) is not None:
            history.measurements.append((metric, int(ts), float(value)))

    for row in _section(data, "sleep", SLEEP_COLUMNS):
        if len(row) != len(SLEEP_COLUMNS):
            raise HistoryError("'sleep' row has the wrong length")
        item = {c: _num(v) for c, v in zip(SLEEP_COLUMNS, row)}
        if item["start_ts"] is None or item["end_ts"] is None:
            continue
        item["start_ts"], item["end_ts"] = int(item["start_ts"]), int(item["end_ts"])
        history.sleep.append(item)

    return history


def load_history_file(path: str | Path) -> History:
    """Read a .json or .json.gz history file."""
    path = Path(path)
    with open(path, "rb") as f:
        gzipped = f.read(2) == b"\x1f\x8b"
    try:
        opener = gzip.open if gzipped else open
        with opener(path, "rb") as f:
            raw = f.read(MAX_BYTES + 1)
    except (OSError, EOFError) as err:
        raise HistoryError("the file could not be read") from err
    if len(raw) > MAX_BYTES:
        raise HistoryError("the file is too large")
    try:
        data = json.loads(raw)
    except ValueError as err:
        raise HistoryError("the file is not valid JSON") from err
    return parse_history(data)
