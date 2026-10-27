"""What each part of the Health page asks for, assembled from the calculations.

Pure Python: no Home Assistant imports. Blocking; run in an executor.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import asdict
from datetime import date, datetime, timedelta, tzinfo
from typing import Any

from . import insights, training
from .metrics import (
    DAY,
    Calculator,
    clock,
    day_bounds,
    load_points_for,
)
from .settings import Settings
from .sources import SOURCES
from .store import IMPORT_DEVICE_ID, Store


def sleep_debt(rows: list[dict[str, Any]], settings: Settings) -> int:
    """Minutes short of the nightly goal over these days (naps count); surplus offsets."""
    total = 0
    for r in rows:
        if r["sleep_total_min"]:
            total += settings.sleep_goal_min - r["sleep_total_min"]
    return max(0, round(total))


def bedtime_tonight(settings: Settings, debt: int) -> dict[str, Any]:
    catch_up = min(round(debt / 3), 30)
    asleep_by = (settings.wake_minutes - settings.sleep_goal_min - catch_up) % 1440
    asleep_by = int(5 * round(asleep_by / 5)) % 1440
    wind_down = (asleep_by - 30) % 1440
    fmt = lambda m: f"{m // 60:02d}:{m % 60:02d}"  # noqa: E731
    return {
        "asleep_by": fmt(asleep_by),
        "wind_down": fmt(wind_down),
        "wake": settings.wake_target,
        "goal_min": settings.sleep_goal_min,
        "catch_up_min": catch_up,
        "debt_min": debt,
    }


def daily_steps_all(store: Store, tz: tzinfo) -> dict[date, int]:
    steps: dict[date, int] = {}
    for h in store.hourly_since(0):
        d = datetime.fromtimestamp(h["hour_ts"], tz).date()
        steps[d] = steps.get(d, 0) + (h["steps"] or 0)
    return steps


def streaks(steps: dict[date, int], goal: int, today: date) -> dict[str, int]:
    current = 0
    d = today if steps.get(today, 0) >= goal else today - timedelta(days=1)
    while steps.get(d, 0) >= goal:
        current += 1
        d -= timedelta(days=1)
    best = run = 0
    prev = None
    for d in sorted(steps):
        if steps[d] >= goal:
            run = run + 1 if prev is not None and (d - prev).days == 1 and steps[prev] >= goal else 1
            best = max(best, run)
        prev = d
    return {"current": current, "best": max(best, current)}


def weight_view(store: Store, settings: Settings, tz: tzinfo) -> dict[str, Any]:
    entries = store.measurements("weight")
    if not entries:
        return {"latest": None, "goal": settings.weight_goal_kg, "entries": []}
    latest = entries[-1]
    month_ago = [e for e in entries if e["ts"] <= latest["ts"] - 30 * DAY]
    since_goal = None
    if settings.weight_goal_set:
        start_ts = day_bounds(date.fromisoformat(settings.weight_goal_set), tz)[1]
        before = [e for e in entries if e["ts"] <= start_ts] or entries[:1]
        since_goal = {"start_kg": before[-1]["value"], "change_kg": round(latest["value"] - before[-1]["value"], 1)}
    progress = None
    if settings.weight_goal_kg and since_goal and since_goal["start_kg"] != settings.weight_goal_kg:
        progress = max(0.0, min(1.0, (since_goal["start_kg"] - latest["value"]) / (since_goal["start_kg"] - settings.weight_goal_kg)))
    return {
        "latest": {"kg": round(latest["value"], 1), "ts": latest["ts"], "date": datetime.fromtimestamp(latest["ts"], tz).date().isoformat()},
        "goal": settings.weight_goal_kg,
        "goal_set": settings.weight_goal_set,
        "since_goal": since_goal,
        "month_change_kg": round(latest["value"] - month_ago[-1]["value"], 1) if month_ago else None,
        "progress": progress,
        "entries": [
            {"ts": e["ts"], "date": datetime.fromtimestamp(e["ts"], tz).date().isoformat(), "kg": round(e["value"], 2), "source": e["source"]}
            for e in entries
        ],
    }


def _slim(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out.pop("baseline", None)
    return out


def day_view(calc: Calculator, store: Store, settings: Settings, day: date, today: date, now_ts: int) -> dict[str, Any]:
    rows = calc.days(day - timedelta(days=36), day, settings)
    row, prev = rows[-1], rows[-2]
    week = rows[-7:]
    debt = sleep_debt(week, settings)
    max_hr = settings.effective_max_hr
    energy = calc.energy(day, row, prev, max_hr)
    load = None
    if row["load"] is not None:
        lo, hi = row["load_range"]
        walk = None
        if row["load"] < lo:
            walk = max(5, math.ceil((load_points_for(lo) - row["load_points"]) / 1.5 / 5) * 5)
        load = {
            "score": row["load"], "range": row["load_range"], "active_min": row["active_min"],
            "peak_hr": row["peak_hr"], "zones": row["zones"], "walk_min": walk, "max_hr": max_hr,
            "max_hr_source": "setting" if settings.max_hr else "age" if settings.age else "default",
        }
    night = row["night"]
    night_detail = calc.night_detail(night) if night and night["source"] == "band" else None
    steps_by_day = daily_steps_all(store, calc.tz)
    start, _ = day_bounds(day, calc.tz)
    is_today = day == today
    return {
        "date": day.isoformat(),
        "is_today": is_today,
        "now_min": (now_ts - start) // 60 if is_today else None,
        "row": _slim(row),
        "baseline": row["baseline"],
        "readiness": row["readiness_detail"],
        "load": load,
        "energy": energy,
        "steps": {"total": row["steps"], "goal": settings.steps_goal, **streaks(steps_by_day, settings.steps_goal, day)},
        "sleep": {
            "night": night,
            "detail": night_detail,
            "naps": row["naps"],
            "total_min": row["sleep_total_min"],
            "debt_min": debt,
            "tonight": bedtime_tonight(settings, debt) if is_today else None,
            "oxygen": insights.oxygen_rule(night, row["baseline"].get("spo2")),
        },
        "weight": weight_view(store, settings, calc.tz),
        "glance": {
            "minutes": calc.minutes_series(day),
            "hourly": calc.hourly_series(day),
            "hr_band": calc.hr_band(day),
        },
        "highlights": insights.overview_highlights(rows, settings, debt),
        "training": training.state(store, settings, today, day),
        "recent": [_slim(r) for r in rows[-14:]],
    }


def range_view(calc: Calculator, settings: Settings, first: date, last: date) -> dict[str, Any]:
    rows = calc.days(first - timedelta(days=28), last, settings)
    shown = rows[28:]
    return {
        "first": first.isoformat(),
        "last": last.isoformat(),
        "days": [_slim(r) for r in shown],
        "sleep_highlights": insights.sleep_highlights(rows, settings),
        "debt_min": sleep_debt(rows[-7:], settings),
        "baseline": rows[-1]["baseline"] if rows else None,
    }


def night_view(calc: Calculator, settings: Settings, day: date) -> dict[str, Any]:
    rows = calc.days(day, day, settings)
    row = rows[0]
    night = row["night"]
    return {
        "date": day.isoformat(),
        "night": night,
        "naps": row["naps"],
        "readiness": row["readiness"],
        "baseline": row["baseline"],
        "detail": calc.night_detail(night) if night and night["source"] == "band" else None,
        "oxygen": insights.oxygen_rule(night, row["baseline"].get("spo2")),
    }


def long_term_sleep(calc: Calculator, settings: Settings, today: date) -> dict[str, Any]:
    """Average sleep and sleep score by month, as far back as records go."""
    store, tz = calc.store, calc.tz
    by_day: dict[date, dict[bool, list[Any]]] = {}
    for s in store.sleep_sessions_since(0):
        end = s["wakeup_ts"] or s["ts"]
        d = datetime.fromtimestamp(end, tz).date()
        by_day.setdefault(d, {True: [], False: []})[s["device_id"] != IMPORT_DEVICE_ID].append(s)
    months: dict[str, dict[str, list[float]]] = {}
    first_band = None
    for d, groups in by_day.items():
        sessions = groups[True] or groups[False]
        total = sum(x["total_min"] or 0 for x in sessions)
        if total < 180:
            continue
        m = months.setdefault(d.strftime("%Y-%m"), {"hours": [], "fitbit": [], "hub": []})
        m["hours"].append(total / 60)
        if not groups[True]:
            scores = [x["score"] for x in sessions if x["score"] is not None]
            if scores:
                m["fitbit"].append(max(scores))
        elif first_band is None or d < first_band:
            first_band = d
    if first_band:
        for r in calc.days(max(first_band, today - timedelta(days=400)), today, settings):
            if r["night"] and r["night"]["source"] == "band":
                months.setdefault(r["date"][:7], {"hours": [], "fitbit": [], "hub": []})["hub"].append(r["night"]["score"])
    out = []
    for key in sorted(months):
        m = months[key]
        out.append({
            "month": key,
            "hours": round(statistics.fmean(m["hours"]), 2) if m["hours"] else None,
            "nights": len(m["hours"]),
            "fitbit_score": round(statistics.fmean(m["fitbit"]), 1) if m["fitbit"] else None,
            "hub_score": round(statistics.fmean(m["hub"]), 1) if m["hub"] else None,
        })
    hours = [m["hours"] for m in out if m["hours"]]
    band = None
    if len(hours) >= 6:
        q = statistics.quantiles(hours, n=10)
        band = [round(q[1], 2), round(q[7], 2)]
    return {"months": out, "normal_range": band}


def settings_view(settings: Settings) -> dict[str, Any]:
    return {**asdict(settings), "effective_max_hr": settings.effective_max_hr}


def sources_view() -> dict[str, Any]:
    return SOURCES


__all__ = [
    "bedtime_tonight", "day_view", "long_term_sleep", "night_view", "range_view",
    "settings_view", "sleep_debt", "sources_view", "streaks", "weight_view", "clock",
]
