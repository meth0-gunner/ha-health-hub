"""Gym and Compex logs, 4-week blocks and rewards.

Rules (confirmed by Nick, 27 Oct 2026):
* Each tap logs one session on the day being viewed; any log can be undone.
* Targets are averages over a block: gym 3 a week, Compex 4 a week, so 12 and
  16 in a 4-week block. Both share the same blocks, Monday to Sunday.
* When a block ends: both targets hit earns 3 rewards, one of them earns 1.
  Then the next block starts.
* "Spend one" takes one reward off the balance.

Pure Python: no Home Assistant imports.
"""

from __future__ import annotations

import math
import time
from datetime import date, timedelta
from typing import Any

from .settings import Settings, update
from .store import Store

KINDS = {"gym": ("push", "pull", "legs"), "compex": (None,)}


class TrainingError(ValueError):
    pass


def anchor(store: Store, settings: Settings, today: date) -> date:
    """The Monday blocks are counted from; set on first use to this week's Monday."""
    if settings.block_anchor:
        return date.fromisoformat(settings.block_anchor)
    monday = today - timedelta(days=today.weekday())
    update(store, {"block_anchor": monday.isoformat()})
    settings.block_anchor = monday.isoformat()
    return monday


def block_for(day: date, start: date, weeks: int) -> tuple[date, date]:
    length = weeks * 7
    index = math.floor((day - start).days / length)
    first = start + timedelta(days=index * length)
    return first, first + timedelta(days=length - 1)


def log(store: Store, day: date, kind: str, variant: str | None) -> int:
    if kind not in KINDS or variant not in KINDS[kind]:
        raise TrainingError("unknown session type")
    return store.add_training(day.isoformat(), int(time.time()), kind, variant)


def _targets(settings: Settings) -> dict[str, int]:
    return {
        "gym": round(settings.gym_per_week * settings.block_weeks),
        "compex": round(settings.compex_per_week * settings.block_weeks),
    }


def settle(store: Store, settings: Settings, today: date) -> None:
    """Credit rewards for every finished block.

    A block already credited is counted again, so a session logged late (on a
    day inside a finished block) still counts.
    """
    start = anchor(store, settings, today)
    credited = {r["block_start"]: r for r in store.rewards_ledger() if r["block_start"]}
    targets = _targets(settings)
    first, last = block_for(today, start, settings.block_weeks)
    # Only blocks from the anchor up to the one before today's.
    b_first = start
    while b_first < first:
        b_last = b_first + timedelta(days=settings.block_weeks * 7 - 1)
        logs = store.training_between(b_first.isoformat(), b_last.isoformat())
        gym = sum(1 for x in logs if x["kind"] == "gym")
        compex = sum(1 for x in logs if x["kind"] == "compex")
        hit_gym, hit_compex = gym >= targets["gym"], compex >= targets["compex"]
        earned = 3 if hit_gym and hit_compex else 1 if hit_gym or hit_compex else 0
        what = "both" if earned == 3 else "gym" if hit_gym else "compex" if hit_compex else "neither"
        reason = f"block {b_first.isoformat()}: gym {gym}/{targets['gym']}, Compex {compex}/{targets['compex']} ({what})"
        before = credited.get(b_first.isoformat())
        if before is None:
            store.add_reward(int(time.mktime((b_last + timedelta(days=1)).timetuple())), earned, reason, b_first.isoformat())
        elif before["delta"] != earned or before["reason"] != reason:
            store.update_block_reward(b_first.isoformat(), earned, reason)
        b_first = b_last + timedelta(days=1)


def spend(store: Store) -> None:
    balance = sum(r["delta"] for r in store.rewards_ledger())
    if balance <= 0:
        raise TrainingError("no rewards to spend")
    store.add_reward(int(time.time()), -1, "spent", None)


def _progress(count: int, target: int, elapsed_days: int, total_days: int, days_left: int, weeks_done: float, ended: bool = False) -> dict[str, Any]:
    # Today isn't over, so the pace counts only the days already finished.
    expected = target * max(elapsed_days - 1, 0) / total_days
    need = max(0, target - count)
    if count >= target:
        status, text = "done", "target hit"
    elif count + 1 >= expected:
        status, text = "on_track", "on track"
    elif count + 3 >= expected:
        status, text = "behind", "slightly behind"
    else:
        status, text = "behind", "behind"
    if ended:
        status, text = ("done", "target hit") if count >= target else ("missed", "missed")
        detail = "block ended"
    elif status == "done":
        detail = f"avg {count / weeks_done:.1f} a week"
    else:
        detail = f"{need} to go in {days_left} day{'s' if days_left != 1 else ''}"
    return {"count": count, "target": target, "status": status, "text": text, "detail": detail, "need": need}


def state(store: Store, settings: Settings, today: date, view_day: date) -> dict[str, Any]:
    settle(store, settings, today)
    start = anchor(store, settings, today)
    weeks = settings.block_weeks
    first, last = block_for(view_day, start, weeks)
    total_days = weeks * 7
    targets = _targets(settings)
    logs = store.training_between(first.isoformat(), last.isoformat())
    if today > last:
        elapsed = total_days
    elif today < first:
        elapsed = 1
    else:
        elapsed = (today - first).days + 1
    days_left = max(0, (last - today).days + 1) if first <= today <= last else 0
    weeks_done = max(elapsed / 7, 1 / 7)
    per_week = []
    for w in range(weeks):
        w_first = first + timedelta(days=7 * w)
        w_last = w_first + timedelta(days=6)
        w_logs = [x for x in logs if w_first.isoformat() <= x["day"] <= w_last.isoformat()]
        per_week.append({
            "first": w_first.isoformat(),
            "gym": sum(1 for x in w_logs if x["kind"] == "gym"),
            "compex": sum(1 for x in w_logs if x["kind"] == "compex"),
            "current": w_first <= today <= w_last,
            "future": w_first > today,
        })
    gym_logs = [x for x in logs if x["kind"] == "gym"]
    compex_logs = [x for x in logs if x["kind"] == "compex"]
    ledger = store.rewards_ledger()
    blocks = []
    for r in reversed(ledger):
        if r["block_start"]:
            b_last = date.fromisoformat(r["block_start"]) + timedelta(days=total_days - 1)
            blocks.append({"first": r["block_start"], "last": b_last.isoformat(), "earned": r["delta"], "reason": r["reason"]})
    last_earned = next((r for r in reversed(ledger) if r["delta"] > 0), None)
    return {
        "block": {
            "first": first.isoformat(),
            "last": last.isoformat(),
            "week": min(weeks, (min(max(today, first), last) - first).days // 7 + 1),
            "weeks": weeks,
            "days_left": days_left,
            "is_current": first <= today <= last,
            "ended": today > last,
            # Blocks before the first one (the anchor) earn no rewards.
            "before_first": last < start,
        },
        "gym": {
            **_progress(len(gym_logs), targets["gym"], elapsed, total_days, days_left, weeks_done, today > last),
            "by_variant": {v: sum(1 for x in gym_logs if x["variant"] == v) for v in KINDS["gym"]},
        },
        "compex": _progress(len(compex_logs), targets["compex"], elapsed, total_days, days_left, weeks_done, today > last),
        "weeks": per_week,
        "day": view_day.isoformat(),
        "day_logs": [x for x in logs if x["day"] == view_day.isoformat()],
        "calendar": logs,
        "rewards": {
            "balance": sum(r["delta"] for r in ledger),
            "earned": sum(r["delta"] for r in ledger if r["delta"] > 0),
            "spent": -sum(r["delta"] for r in ledger if r["delta"] < 0),
            "last_earned": {
                "ts": last_earned["ts"],
                "delta": last_earned["delta"],
                "block": last_earned["block_start"],
                "block_last": (
                    date.fromisoformat(last_earned["block_start"]) + timedelta(days=total_days - 1)
                ).isoformat() if last_earned["block_start"] else None,
            }
            if last_earned
            else None,
            "ledger": [
                {"ts": r["ts"], "delta": r["delta"], "reason": r["reason"], "block": r["block_start"]}
                for r in reversed(ledger)
            ][:50],
        },
        "past_blocks": blocks[:12],
        "targets": {**targets, "gym_per_week": settings.gym_per_week, "compex_per_week": settings.compex_per_week},
    }
