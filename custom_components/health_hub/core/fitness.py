"""Cardio fitness: the 1-mile walk test, a rough heart-rate estimate and fitness age.

Pure Python: no Home Assistant imports.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, tzinfo
from typing import Any

from .store import Store

MILE_KM = 1.609
LB_PER_KG = 2.20462
WEIGHT_MAX_AGE_DAYS = 90  # a weigh-in older than this isn't used for a test

# Healthy Norwegian adults in the HUNT 3 fitness study, treadmill-measured
# VO2max in mL/kg/min by age group: (first age, last age, mean, SD).
# Loe et al. 2013, PLoS ONE 8(5): e64319, Table 2.
REFERENCE = {
    "male": [(20, 29, 54.4, 8.4), (30, 39, 49.1, 7.5), (40, 49, 47.2, 7.7), (50, 59, 42.6, 7.4), (60, 69, 39.2, 6.7), (70, 90, 35.3, 6.5)],
    "female": [(20, 29, 43.0, 7.7), (30, 39, 40.0, 6.8), (40, 49, 38.4, 6.9), (50, 59, 34.4, 5.7), (60, 69, 31.1, 5.1), (70, 90, 28.3, 5.2)],
}
# Mid-ages used to draw a line through the group means (70+ taken as 75).
MIDS = [25, 35, 45, 55, 65, 75]

# Heart-rate ratio factors: 15.3 for well-trained men (Uth 2004), about 12 for
# men around 50 in the general population (Voutilainen 2020).
RATIO_LOW, RATIO_HIGH = 12.0, 15.3


class FitnessError(ValueError):
    pass


def rockport(weight_kg: float, age: float, male: bool, minutes: float, hr: float) -> float:
    """VO2max (mL/kg/min) from a 1-mile walk as fast as possible (Kline et al. 1987)."""
    return (
        132.853
        - 0.0769 * weight_kg * LB_PER_KG
        - 0.3877 * age
        + 6.315 * (1 if male else 0)
        - 3.2649 * minutes
        - 0.1565 * hr
    )


def reference_for(sex: str, age: int) -> dict[str, float] | None:
    for lo, hi, mean, sd in REFERENCE.get(sex, []):
        if lo <= age <= hi:
            return {"mean": mean, "sd": sd, "from": lo, "to": hi}
    return None


def fitness_age(sex: str, vo2: float) -> dict[str, Any]:
    """The age at which healthy people of the same sex in HUNT average this VO2max."""
    means = [r[2] for r in REFERENCE[sex]]
    if vo2 >= means[0]:
        return {"age": MIDS[0], "bound": "under"}
    if vo2 <= means[-1]:
        return {"age": MIDS[-1], "bound": "over"}
    for (a0, m0), (a1, m1) in zip(zip(MIDS, means), zip(MIDS[1:], means[1:]), strict=False):
        if m1 <= vo2 <= m0:
            return {"age": round(a0 + (m0 - vo2) / (m0 - m1) * (a1 - a0)), "bound": None}
    return {"age": None, "bound": None}


def rate(sex: str, age: int, vo2: float) -> str | None:
    ref = reference_for(sex, age)
    if ref is None:
        return None
    if vo2 >= ref["mean"]:
        return "good"
    if vo2 >= ref["mean"] - ref["sd"]:
        return "fair"
    return "low"


def ratio_range(max_hr: float, rest: float | None) -> list[float] | None:
    if not rest:
        return None
    return [round(RATIO_LOW * max_hr / rest, 1), round(RATIO_HIGH * max_hr / rest, 1)]


# ------------------------------------------------------------------ storage


def _weight_on(store: Store, ts: int) -> dict[str, Any] | None:
    best = None
    for w in store.measurements("weight"):
        if w["ts"] <= ts + 86400 and w["ts"] >= ts - WEIGHT_MAX_AGE_DAYS * 86400:
            best = w
    return best


def band_hr_at(store: Store, ts: int) -> int | None:
    """The band's highest reading in the minute either side of the finish."""
    rows = store.minutes_between(ts - 90, ts + 90)
    vals = [r["heart_rate"] for r in rows if r["heart_rate"]]
    return max(vals) if vals else None


def log_walk_test(store: Store, finish_ts: int, seconds: int, hr: int | None) -> dict[str, Any]:
    if not 300 <= seconds <= 3600:
        raise FitnessError("the walk time should be between 5 and 60 minutes")
    if _weight_on(store, finish_ts) is None:
        raise FitnessError("log a weigh-in on the Body page first (the test needs your weight from the last 90 days)")
    source = "manual"
    if hr is None:
        hr = band_hr_at(store, finish_ts)
        source = "band"
        if hr is None:
            raise FitnessError("the band has no heart rate at that finish time; enter your heart rate at the finish")
    if not 60 <= hr <= 230:
        raise FitnessError("heart rate at the finish should be between 60 and 230")
    store.add_measurement(finish_ts, "walk_test_s", float(seconds), "manual")
    store.add_measurement(finish_ts, "walk_test_hr", float(hr), source)
    return {"ts": finish_ts, "seconds": seconds, "hr": hr, "hr_from": source}


def delete_walk_test(store: Store, ts: int) -> bool:
    done = store.delete_measurement(ts, "walk_test_s", "manual")
    for source in ("manual", "band"):
        store.delete_measurement(ts, "walk_test_hr", source)
    return done


def walk_tests(store: Store, tz: tzinfo, sex: str | None, age: int | None) -> list[dict[str, Any]]:
    """Every walk test, oldest first, with its VO2max worked out where possible."""
    hrs = {m["ts"]: m for m in store.measurements("walk_test_hr")}
    out = []
    for t in store.measurements("walk_test_s"):
        h = hrs.get(t["ts"])
        if h is None:
            continue
        w = _weight_on(store, t["ts"])
        entry: dict[str, Any] = {
            "ts": t["ts"],
            "date": datetime.fromtimestamp(t["ts"], tz).date().isoformat(),
            "seconds": int(t["value"]),
            "hr": int(h["value"]),
            "hr_from": h["source"],
            "weight_kg": w["value"] if w else None,
            "vo2max": None,
            "fitness_age": None,
        }
        if w and sex in REFERENCE and age:
            # Age at the time of the test, from today's age.
            years_ago = (datetime.now(tz).date() - date.fromisoformat(entry["date"])).days / 365.25
            vo2 = rockport(w["value"], age - years_ago, sex == "male", t["value"] / 60, h["value"])
            entry["vo2max"] = round(vo2, 1)
            entry["fitness_age"] = fitness_age(sex, vo2)
        out.append(entry)
    return out


def finish_ts(day: date, clock: str, tz: tzinfo) -> int:
    try:
        hh, mm = (int(x) for x in clock.split(":")[:2])
        moment = datetime.combine(day, datetime.min.time(), tz).replace(hour=hh, minute=mm)
    except (ValueError, TypeError) as err:
        raise FitnessError("finish time must look like 07:45") from err
    if moment > datetime.now(tz) + timedelta(minutes=5):
        raise FitnessError("that finish time is in the future")
    return int(moment.timestamp())
