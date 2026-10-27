"""Build Home Assistant long-term statistics rows from the store.

Every statistic is hourly, as Home Assistant requires:

* Summed metrics (steps, distance, active calories) carry a running total, so
  charts can show the change per hour, day, week or month.
* Averaged metrics (heart rate, stress, SpO2) carry the hour's mean, min and max.
* Once-a-day metrics (resting heart rate, sleep, weight...) are written as a
  single row at local midnight of the day they belong to, so a daily chart
  shows the value and a monthly chart shows the average.

Band data and imported history (for example Fitbit) feed the same statistics,
so each chart runs continuously from one to the other. Where both have a value
for the same day or hour, the band's wins.

Pure Python: returns plain dicts that the Home Assistant layer wraps.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone, tzinfo
from typing import Any

from .store import IMPORT_DEVICE_ID, Store, hour_start


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
    StatDef("hrv", "Heart rate variability", "ms", "daily"),
    StatDef("respiratory_rate", "Breathing rate", "br/min", "daily"),
    StatDef("weight", "Weight", "kg", "daily"),
    StatDef("vitality_score", "Vitality score", None, "daily"),
    StatDef("sleep_duration", "Sleep", "h", "daily"),
    StatDef("deep_sleep", "Deep sleep", "h", "daily"),
    StatDef("light_sleep", "Light sleep", "h", "daily"),
    StatDef("rem_sleep", "REM sleep", "h", "daily"),
    StatDef("awake_in_bed", "Awake in bed", "h", "daily"),
    StatDef("sleep_score", "Sleep score", None, "daily"),
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
        if not h[f"{p}_n"] or h[f"{p}_mean"] is None:
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


def _on_the_hour(local: datetime) -> datetime:
    # Zones with half-hour offsets do not land on an hour; round down.
    return local.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def local_midnight(ts: int, tz: tzinfo) -> datetime:
    """Local midnight of the day containing `ts`, as a UTC datetime on the hour."""
    local = datetime.fromtimestamp(ts, tz)
    return _on_the_hour(local.replace(hour=0, minute=0, second=0, microsecond=0))


def date_midnight(day: str, tz: tzinfo) -> datetime:
    """Local midnight of a YYYY-MM-DD date, as a UTC datetime on the hour."""
    d = date.fromisoformat(day)
    return _on_the_hour(datetime(d.year, d.month, d.day, tzinfo=tz))


def _series(per_day: dict[datetime, float]) -> list[dict[str, Any]]:
    return [_daily(day, round(per_day[day], 2)) for day in sorted(per_day)]


def daily_rows(store: Store, tz: tzinfo) -> dict[str, list[dict[str, Any]]]:
    """Once-a-day values from the band's daily summaries and imported history."""
    resting: dict[datetime, float] = {}
    for day, value in store.daily_metric("resting_heart_rate"):
        resting[date_midnight(day, tz)] = value
    vitality: dict[datetime, float] = {}
    for d in store.daily_since(0):  # the band's summaries win over imports
        start = _utc(hour_start(d["ts"]))
        if d["hr_resting"] is not None:
            resting[start] = d["hr_resting"]
        if d["vitality"] is not None:
            vitality[start] = d["vitality"]

    out = {"resting_heart_rate": _series(resting), "vitality_score": _series(vitality)}
    for metric in ("hrv", "respiratory_rate"):
        out[metric] = _series({date_midnight(d, tz): v for d, v in store.daily_metric(metric)})

    weight: dict[datetime, float] = {}
    for ts, value in store.measurement_series("weight"):  # oldest first: last of the day wins
        weight[local_midnight(ts, tz)] = value
    out["weight"] = _series(weight)
    return out


def sleep_rows(store: Store, tz: tzinfo) -> dict[str, list[dict[str, Any]]]:
    """Sleep totals, credited to the day you woke up.

    Several sessions on one day (a nap) are added together. If the band and an
    imported history both recorded a day, only the band's sessions count.
    """
    keys = {
        "sleep_duration": "total_min",
        "deep_sleep": "deep_min",
        "light_sleep": "light_min",
        "rem_sleep": "rem_min",
        "awake_in_bed": "awake_min",
    }
    by_day: dict[datetime, dict[bool, list[Any]]] = {}
    for s in store.sleep_sessions_since(0):
        day = local_midnight(s["wakeup_ts"] or s["ts"], tz)
        by_day.setdefault(day, {True: [], False: []})[s["device_id"] != IMPORT_DEVICE_ID].append(s)

    out: dict[str, list[dict[str, Any]]] = {k: [] for k in (*keys, "sleep_score")}
    for day in sorted(by_day):
        sessions = by_day[day][True] or by_day[day][False]
        for key, column in keys.items():
            values = [s[column] for s in sessions if s[column] is not None]
            if values:
                out[key].append(_daily(day, round(sum(values) / 60.0, 2)))
        scores = [s["score"] for s in sessions if s["score"] is not None]
        if scores:
            out["sleep_score"].append(_daily(day, max(scores)))
    return out


def rows_for_change(
    store: Store, kind: str, min_ts: int, tz: tzinfo
) -> dict[str, list[dict[str, Any]]]:
    """Statistics rows affected by new data of one kind.

    Hourly series are rewritten from the first changed hour. Daily series are
    small (one row a day), so they are always rewritten whole.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    if kind == "minute":
        for stat in STATISTICS:
            if stat.kind == "sum":
                out[stat.key] = sum_rows(store, stat, min_ts)
            elif stat.kind == "mean":
                out[stat.key] = mean_rows(store, stat, min_ts)
    elif kind == "daily":
        out.update(daily_rows(store, tz))
    elif kind == "sleep_session":
        out.update(sleep_rows(store, tz))
    return {k: v for k, v in out.items() if v}


def rows_for_full_rebuild(store: Store, tz: tzinfo) -> dict[str, list[dict[str, Any]]]:
    """Every statistic from the start of the record."""
    out: dict[str, list[dict[str, Any]]] = {}
    for kind in ("minute", "daily", "sleep_session"):
        out.update(rows_for_change(store, kind, 0, tz))
    return out
