"""Build Home Assistant long-term statistics rows from the store.

Every statistic is hourly, as Home Assistant requires:

* Summed metrics (steps, distance, active calories) carry a running total, so
  charts can show the change per hour, day, week or month.
* Averaged metrics (heart rate, stress, SpO2) carry the hour's mean, min and max.
* Once-a-day metrics (resting heart rate, sleep) are written as a single row at
  local midnight of the day they belong to, so a daily chart shows the value
  and a monthly chart shows the average.

Pure Python: returns plain dicts that the Home Assistant layer wraps.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from typing import Any

from .store import Store, hour_start


@dataclass(frozen=True)
class StatDef:
    key: str
    name: str
    unit: str | None
    kind: str  # "sum", "mean" or "daily"
    column: str | None = None  # hourly column for "sum"; prefix for "mean"


STATISTICS: tuple[StatDef, ...] = (
    StatDef("steps", "Steps", "steps", "sum", "steps"),
    StatDef("distance", "Distance", "m", "sum", "distance_m"),
    StatDef("active_calories", "Active calories", "kcal", "sum", "active_calories"),
    StatDef("heart_rate", "Heart rate", "bpm", "mean", "hr"),
    StatDef("stress", "Stress", None, "mean", "stress"),
    StatDef("spo2", "Blood oxygen", "%", "mean", "spo2"),
    StatDef("resting_heart_rate", "Resting heart rate", "bpm", "daily"),
    StatDef("vitality_score", "Vitality score", None, "daily"),
    StatDef("sleep_duration", "Sleep", "h", "daily"),
    StatDef("deep_sleep", "Deep sleep", "h", "daily"),
    StatDef("light_sleep", "Light sleep", "h", "daily"),
    StatDef("rem_sleep", "REM sleep", "h", "daily"),
    StatDef("awake_in_bed", "Awake in bed", "h", "daily"),
)
STATS_BY_KEY = {s.key: s for s in STATISTICS}


def _utc(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, timezone.utc)


def sum_rows(store: Store, stat: StatDef, from_hour: int) -> list[dict[str, Any]]:
    """Hourly rows with a running total, rewritten from `from_hour` onwards."""
    from_hour = hour_start(from_hour)
    running = store.hourly_sum_before(from_hour, stat.column)
    rows = []
    for h in store.hourly_since(from_hour):
        value = h[stat.column] or 0
        running += value
        rows.append({"start": _utc(h["hour_ts"]), "state": value, "sum": running})
    return rows


def mean_rows(store: Store, stat: StatDef, from_hour: int) -> list[dict[str, Any]]:
    """Hourly mean, min and max, skipping hours with no readings."""
    p = stat.column
    rows = []
    for h in store.hourly_since(hour_start(from_hour)):
        if not h[f"{p}_n"]:
            continue
        rows.append(
            {
                "start": _utc(h["hour_ts"]),
                "mean": round(h[f"{p}_mean"], 2),
                "min": h[f"{p}_min"],
                "max": h[f"{p}_max"],
            }
        )
    return rows


def _daily(start: datetime, value: float) -> dict[str, Any]:
    return {"start": start, "mean": value, "min": value, "max": value}


def daily_summary_rows(store: Store, from_ts: int) -> dict[str, list[dict[str, Any]]]:
    """Resting heart rate and vitality, one row per day at local midnight."""
    out: dict[str, list[dict[str, Any]]] = {"resting_heart_rate": [], "vitality_score": []}
    for d in store.daily_since(from_ts):
        start = _utc(hour_start(d["ts"]))
        if d["hr_resting"] is not None:
            out["resting_heart_rate"].append(_daily(start, d["hr_resting"]))
        if d["vitality"] is not None:
            out["vitality_score"].append(_daily(start, d["vitality"]))
    return out


def local_midnight(ts: int, tz: tzinfo) -> datetime:
    """Local midnight of the day containing `ts`, as a UTC datetime on the hour."""
    local = datetime.fromtimestamp(ts, tz)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    utc = midnight.astimezone(timezone.utc)
    # Zones with half-hour offsets do not land on an hour; round down.
    return utc.replace(minute=0, second=0, microsecond=0)


def sleep_rows(store: Store, from_ts: int, tz: tzinfo) -> dict[str, list[dict[str, Any]]]:
    """Sleep totals, credited to the day you woke up.

    If one day has several sessions (a nap), their durations are added.
    """
    keys = {
        "sleep_duration": "total_min",
        "deep_sleep": "deep_min",
        "light_sleep": "light_min",
        "rem_sleep": "rem_min",
        "awake_in_bed": "awake_min",
    }
    per_day: dict[datetime, dict[str, float]] = {}
    for s in store.sleep_sessions_since(from_ts - 2 * 86400):
        wake = s["wakeup_ts"] or s["ts"]
        day = local_midnight(wake, tz)
        totals = per_day.setdefault(day, {k: 0.0 for k in keys})
        for key, column in keys.items():
            totals[key] += (s[column] or 0) / 60.0
    out: dict[str, list[dict[str, Any]]] = {k: [] for k in keys}
    for day in sorted(per_day):
        for key in keys:
            out[key].append(_daily(day, round(per_day[day][key], 2)))
    return out


def rows_for_change(
    store: Store, kind: str, min_ts: int, tz: tzinfo
) -> dict[str, list[dict[str, Any]]]:
    """All statistics rows affected by new data of one kind since `min_ts`."""
    out: dict[str, list[dict[str, Any]]] = {}
    if kind == "minute":
        for stat in STATISTICS:
            if stat.kind == "sum":
                out[stat.key] = sum_rows(store, stat, min_ts)
            elif stat.kind == "mean":
                out[stat.key] = mean_rows(store, stat, min_ts)
    elif kind == "daily":
        out.update(daily_summary_rows(store, min_ts))
    elif kind == "sleep_session":
        out.update(sleep_rows(store, min_ts, tz))
    return {k: v for k, v in out.items() if v}


def rows_for_full_rebuild(store: Store, tz: tzinfo) -> dict[str, list[dict[str, Any]]]:
    """Every statistic from the start of the record."""
    out: dict[str, list[dict[str, Any]]] = {}
    for kind in ("minute", "daily", "sleep_session"):
        out.update(rows_for_change(store, kind, 0, tz))
    return out

