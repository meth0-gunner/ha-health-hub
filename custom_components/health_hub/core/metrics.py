"""Health Hub's own calculations: sleep score, readiness, day load and energy.

Everything is worked out from the store on request, per local calendar day,
and compared with the owner's own recent figures (usually the previous 30
days). The formulas are Health Hub's own and are described to the user under
"Why?" on the Health page; where a published threshold is used, its source is
in `sources.py`.

Pure Python: no Home Assistant imports. Blocking; run in an executor.
"""

from __future__ import annotations

import math
import statistics
import threading
import time as _time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Any

from .settings import Settings
from .store import IMPORT_DEVICE_ID, Store

DAY = 86400
MAIN_SLEEP_MIN = 180
BASELINE_DAYS = 30
MIN_BASELINE = 5
STAGES = {2: "deep", 3: "light", 4: "rem", 5: "awake"}

# Weights, shown on the page under "Why?".
SLEEP_WEIGHTS = {"duration": 30, "restorative": 25, "interruptions": 15, "timing": 15, "heart": 15}
READINESS_WEIGHTS = {"sleep": 35, "resting_hr": 25, "overnight_stress": 25, "timing": 10, "load": 5}


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def day_bounds(day: date, tz: tzinfo) -> tuple[int, int]:
    start = datetime.combine(day, time(0), tz)
    end = datetime.combine(day + timedelta(days=1), time(0), tz)
    return int(start.timestamp()), int(end.timestamp())


def local(ts: int, tz: tzinfo) -> datetime:
    return datetime.fromtimestamp(ts, tz)


def minute_of_day(ts: int, tz: tzinfo) -> int:
    t = local(ts, tz)
    return t.hour * 60 + t.minute


def clock(ts: int | None, tz: tzinfo) -> str | None:
    return local(ts, tz).strftime("%H:%M") if ts else None


def from_noon(ts: int, tz: tzinfo) -> int:
    """Clock time as minutes after midday, so bedtimes either side of midnight compare."""
    return (minute_of_day(ts, tz) - 720) % 1440


def _mean(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.fmean(vals) if vals else None


def _r(v: float | None, n: int = 1) -> float | None:
    return None if v is None else round(v, n)


def label_for(score: float | None, bands: tuple[tuple[int, str], ...]) -> str | None:
    if score is None:
        return None
    for floor, name in bands:
        if score >= floor:
            return name
    return bands[-1][1]


SLEEP_LABELS = ((85, "Excellent"), (70, "Good"), (55, "Fair"), (0, "Poor"))
READINESS_LABELS = ((85, "Excellent"), (70, "Good"), (50, "Fair"), (0, "Low"))


# ----------------------------------------------------------------- day load


def hr_zone(hr: int, rest: float, max_hr: float) -> int:
    """0-5 by heart-rate reserve (Karvonen): 30, 45, 60, 75 and 85% of reserve."""
    reserve = max(max_hr - rest, 40)
    frac = (hr - rest) / reserve
    for zone, floor in ((5, 0.85), (4, 0.75), (3, 0.60), (2, 0.45), (1, 0.30)):
        if frac >= floor:
            return zone
    return 0


def load_from_hist(
    hist: dict[int, int], brisk: dict[int, int], rest: float, max_hr: float
) -> dict[str, Any]:
    """Day load (0-100) from a histogram of minute heart rates.

    Each minute scores its zone (1-5); a brisk-walking minute (100+ steps)
    counts at least 1. The day's points are squashed onto 0-100 so that very
    hard days approach but never pass 100.
    """
    zones = Counter()
    for hr, n in hist.items():
        zones[hr_zone(hr, rest, max_hr)] += n
    lifted = 0
    for hr, n in brisk.items():
        if hr_zone(hr, rest, max_hr) == 0:
            lifted += n
    zones[0] -= lifted
    zones[1] += lifted
    points = sum(z * n for z, n in zones.items())
    return {
        "points": points,
        "load": round(100 * (1 - math.exp(-points / 120))),
        "active_min": sum(n for z, n in zones.items() if z >= 1),
        "zones": {str(z): zones.get(z, 0) for z in range(1, 6)},
    }


def load_points_for(load: float) -> float:
    load = min(load, 99.5)
    return -120 * math.log(1 - load / 100)


def recommended_load(readiness: float | None) -> tuple[int, int]:
    if readiness is None:
        return (35, 60)
    if readiness >= 75:
        return (50, 75)
    if readiness >= 55:
        return (35, 60)
    return (15, 40)


# ---------------------------------------------------------------- the store


@dataclass
class Night:
    day: date
    bed_ts: int
    wake_ts: int
    asleep_min: int
    deep_min: int | None
    light_min: int | None
    rem_min: int | None
    awake_min: int | None
    source: str  # band | imported
    fitbit_score: float | None
    overnight: dict[str, Any] | None = None
    awake_spells: int | None = None


@dataclass
class RawDay:
    day: date
    steps: int = 0
    distance_km: float = 0.0
    active_kcal: int = 0
    hr_avg: float | None = None
    stress_avg: float | None = None
    stress_peak_window: int | None = None  # 0-11: two-hour window with the highest stress
    worn_hours: float | None = None
    peak_hr: int | None = None
    hr_hist: dict[int, int] = field(default_factory=dict)
    brisk_hist: dict[int, int] = field(default_factory=dict)
    sources: tuple[str, ...] = ()
    rhr: float | None = None
    vitality: int | None = None
    night: Night | None = None
    naps: list[Night] = field(default_factory=list)
    has_minutes: bool = False


class Calculator:
    """Works out per-day figures, caching the raw parts until data changes."""

    def __init__(self, store: Store, tz: tzinfo) -> None:
        self.store = store
        self.tz = tz
        self._raw: dict[date, RawDay] = {}
        self._imported: dict[str, dict[str, float]] | None = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------ caching

    def invalidate(self, start_ts: int | None = None, end_ts: int | None = None) -> None:
        with self._lock:
            if start_ts is None:
                self._raw.clear()
                self._imported = None
                return
            first = local(start_ts - DAY, self.tz).date()
            last = local((end_ts or start_ts) + 2 * DAY, self.tz).date()
            for d in [d for d in self._raw if first <= d <= last]:
                del self._raw[d]

    def _imports(self) -> dict[str, dict[str, float]]:
        if self._imported is None:
            self._imported = {
                m: dict(self.store.daily_metric(m))
                for m in ("resting_heart_rate", "hrv", "respiratory_rate")
            }
        return self._imported

    def raw(self, day: date) -> RawDay:
        today = datetime.now(self.tz).date()
        with self._lock:
            cached = self._raw.get(day)
            if cached is not None and day < today:
                return cached
        raw = self._build_raw(day)
        with self._lock:
            self._raw[day] = raw
        return raw

    # --------------------------------------------------------- raw figures

    def _build_raw(self, day: date) -> RawDay:
        s, tz = self.store, self.tz
        start, end = day_bounds(day, tz)
        raw = RawDay(day=day)
        sources: set[str] = set()
        hr_sum = hr_n = st_sum = st_n = 0.0
        windows = [[0.0, 0] for _ in range(12)]
        for h in s.hourly_between(start, end):
            raw.steps += h["steps"] or 0
            raw.distance_km += (h["distance_m"] or 0) / 1000
            raw.active_kcal += h["active_calories"] or 0
            sources.add("band" if (h["source"] or "band") == "band" else "imported")
            if h["hr_n"] and h["hr_mean"] is not None:
                hr_sum += h["hr_mean"] * h["hr_n"]
                hr_n += h["hr_n"]
            if h["stress_n"] and h["stress_mean"] is not None:
                st_sum += h["stress_mean"] * h["stress_n"]
                st_n += h["stress_n"]
                w = windows[local(h["hour_ts"], tz).hour // 2]
                w[0] += h["stress_mean"] * h["stress_n"]
                w[1] += h["stress_n"]
        raw.distance_km = round(raw.distance_km, 2)
        raw.hr_avg = _r(hr_sum / hr_n) if hr_n else None
        raw.stress_avg = _r(st_sum / st_n) if st_n else None
        means = [(w[0] / w[1], i) for i, w in enumerate(windows) if w[1] >= 30]
        raw.stress_peak_window = max(means)[1] if means else None
        raw.sources = tuple(sorted(sources))

        worn = 0
        for m in s.minutes_between(start, end):
            hr = m["heart_rate"]
            if hr is None:
                continue
            worn += 1
            raw.hr_hist[hr] = raw.hr_hist.get(hr, 0) + 1
            if (m["steps"] or 0) >= 100:
                raw.brisk_hist[hr] = raw.brisk_hist.get(hr, 0) + 1
            if raw.peak_hr is None or hr > raw.peak_hr:
                raw.peak_hr = hr
        raw.has_minutes = worn > 0
        raw.worn_hours = round(worn / 60, 1) if worn else None

        for row in s.daily_between(start - 14 * 3600, end + 14 * 3600):
            if local(row["ts"] + 6 * 3600, tz).date() == day or local(row["ts"], tz).date() == day:
                if row["hr_resting"] is not None:
                    raw.rhr = row["hr_resting"]
                if row["vitality"] is not None:
                    raw.vitality = row["vitality"]
        if raw.rhr is None:
            raw.rhr = self._imports()["resting_heart_rate"].get(day.isoformat())

        sessions = [dict(r) for r in s.sleep_sessions_between(start, end)]
        band = [x for x in sessions if x["device_id"] != IMPORT_DEVICE_ID]
        chosen = band or [x for x in sessions if x["device_id"] == IMPORT_DEVICE_ID]
        nights = [self._night(day, x) for x in chosen if x["total_min"]]
        main = max(nights, key=lambda n: n.asleep_min, default=None)
        if main and main.asleep_min >= MAIN_SLEEP_MIN:
            raw.night = main
            raw.naps = [n for n in nights if n is not main]
        else:
            raw.naps = nights
        if raw.night and raw.night.source == "band":
            self._overnight(raw.night)
        return raw

    def _night(self, day: date, row: dict[str, Any]) -> Night:
        return Night(
            day=day,
            bed_ts=row["ts"],
            wake_ts=row["wakeup_ts"] or row["ts"] + (row["total_min"] or 0) * 60,
            asleep_min=row["total_min"] or 0,
            deep_min=row["deep_min"],
            light_min=row["light_min"],
            rem_min=row["rem_min"],
            awake_min=row["awake_min"],
            source="band" if row["device_id"] != IMPORT_DEVICE_ID else "imported",
            fitbit_score=row["score"] if row["device_id"] == IMPORT_DEVICE_ID else None,
        )

    def _overnight(self, night: Night) -> None:
        w = self.store.window_stats(night.bed_ts, night.wake_ts)
        if w["hr_n"] or w["stress_n"] or w["spo2_n"]:
            night.overnight = {
                "hr_avg": _r(w["hr_avg"]),
                "hr_min": w["hr_min"],
                "stress_avg": _r(w["stress_avg"]),
                "spo2_avg": _r(w["spo2_avg"]),
                "spo2_min": w["spo2_min"],
                "spo2_n": w["spo2_n"],
                "spo2_below_90": w["spo2_below_90"],
            }
        stages = self.store.stages_between(night.bed_ts, night.wake_ts)
        if stages:
            spells, prev = 0, None
            for _ts, stage in stages:
                if stage == 5 and prev != 5:
                    spells += 1
                prev = stage
            night.awake_spells = spells

    # ------------------------------------------------------------- derived

    def days(self, first: date, last: date, settings: Settings) -> list[dict[str, Any]]:
        """Every figure per day from `first` to `last`, with baselines from before."""
        span = (last - first).days + 1
        raws = [self.raw(first + timedelta(days=i - BASELINE_DAYS - 1)) for i in range(span + BASELINE_DAYS + 1)]
        imports = self._imports()
        out = []
        for i in range(BASELINE_DAYS + 1, len(raws)):
            raw, prior, prev = raws[i], raws[i - BASELINE_DAYS:i], raws[i - 1]
            out.append(self._derive(raw, prior, prev, settings, imports))
        return out

    def _baselines(self, prior: list[RawDay]) -> dict[str, float | None]:
        def base(values: list[float | None]) -> float | None:
            vals = [v for v in values if v is not None]
            return statistics.fmean(vals) if len(vals) >= MIN_BASELINE else None

        nights = [r.night for r in prior if r.night]
        over = [n.overnight for n in nights if n.overnight]
        ratios = [
            (n.deep_min + n.rem_min) / n.asleep_min
            for n in nights
            if n.deep_min is not None and n.rem_min is not None and n.asleep_min
        ]
        return {
            "rhr": base([r.rhr for r in prior]),
            "stress": base([o["stress_avg"] for o in over]),
            "night_hr": base([o["hr_avg"] for o in over]),
            "spo2": base([o["spo2_avg"] for o in over]),
            "restorative": base(ratios),
            "deep": base([n.deep_min for n in nights]),
            "light": base([n.light_min for n in nights]),
            "rem": base([n.rem_min for n in nights]),
            "awake": base([n.awake_min for n in nights]),
            "asleep": base([n.asleep_min for n in nights]),
            "steps": base([r.steps for r in prior if r.steps]),
            "nights": len(nights),
        }

    def sleep_score(self, night: Night, base: dict[str, Any], settings: Settings) -> dict[str, Any]:
        parts: dict[str, dict[str, Any]] = {}
        ratio = night.asleep_min / settings.sleep_goal_min
        parts["duration"] = {"s": clamp((ratio - 0.5) / 0.5)}
        if night.deep_min is not None and night.rem_min is not None and night.asleep_min:
            mine = (night.deep_min + night.rem_min) / night.asleep_min
            ref = base["restorative"] or 0.42
            parts["restorative"] = {"s": clamp(mine / ref), "percent": round(100 * mine)}
        if night.awake_min is not None:
            parts["interruptions"] = {"s": clamp(1 - night.awake_min / 60)}
        target = (settings.bed_minutes + 15 - 720) % 1440  # allow 15 minutes to fall asleep
        late = from_noon(night.bed_ts, self.tz) - target
        parts["timing"] = {"s": clamp(1 - max(0, abs(late) - 15) / 120), "late_min": late}
        heart = []
        if night.overnight:
            o = night.overnight
            if o["hr_avg"] is not None and base["night_hr"] is not None:
                heart.append(clamp(1 - max(0, o["hr_avg"] - base["night_hr"]) / 10))
            if o["stress_avg"] is not None and base["stress"] is not None:
                heart.append(clamp(1 - max(0, o["stress_avg"] - base["stress"]) / 15))
        if heart:
            parts["heart"] = {"s": statistics.fmean(heart)}
        total_w = sum(SLEEP_WEIGHTS[k] for k in parts)
        score = round(100 * sum(SLEEP_WEIGHTS[k] * p["s"] for k, p in parts.items()) / total_w)
        for k, p in parts.items():
            p["s"] = round(p["s"], 2)
            p["weight"] = SLEEP_WEIGHTS[k]
        return {"score": score, "label": label_for(score, SLEEP_LABELS), "parts": parts}

    def readiness(
        self, raw: RawDay, sleep: dict[str, Any] | None, base: dict[str, Any], prev: RawDay, prev_load: int | None
    ) -> dict[str, Any] | None:
        if sleep is None:
            return None
        parts: dict[str, dict[str, Any]] = {"sleep": {"s": sleep["score"] / 100}}
        if raw.rhr is not None and base["rhr"] is not None:
            diff = raw.rhr - base["rhr"]
            parts["resting_hr"] = {"s": clamp(0.7 - 0.06 * diff), "value": raw.rhr, "diff": round(diff, 1)}
        o = raw.night.overnight if raw.night else None
        if o and o["stress_avg"] is not None and base["stress"] is not None:
            diff = o["stress_avg"] - base["stress"]
            parts["overnight_stress"] = {"s": clamp(0.7 - 0.04 * diff), "value": o["stress_avg"], "diff": round(diff, 1)}
        timing = sleep["parts"].get("timing")
        if timing:
            parts["timing"] = {"s": timing["s"], "late_min": timing["late_min"]}
        if prev_load is not None:
            parts["load"] = {"s": clamp(1 - max(0, prev_load - 70) / 30), "value": prev_load}
        total_w = sum(READINESS_WEIGHTS[k] for k in parts)
        score = round(100 * sum(READINESS_WEIGHTS[k] * p["s"] for k, p in parts.items()) / total_w)
        for k, p in parts.items():
            p["s"] = round(p["s"], 2)
            p["weight"] = READINESS_WEIGHTS[k]
        return {
            "score": score,
            "label": label_for(score, READINESS_LABELS),
            "parts": parts,
            "summary": readiness_summary(score, parts),
        }

    def _derive(
        self, raw: RawDay, prior: list[RawDay], prev: RawDay, settings: Settings, imports: dict[str, dict[str, float]]
    ) -> dict[str, Any]:
        base = self._baselines(prior)
        rest = raw.rhr or base["rhr"] or 60
        max_hr = settings.effective_max_hr
        load = load_from_hist(raw.hr_hist, raw.brisk_hist, rest, max_hr) if raw.has_minutes else None
        prev_rest = prev.rhr or base["rhr"] or 60
        prev_load = (
            load_from_hist(prev.hr_hist, prev.brisk_hist, prev_rest, max_hr)["load"] if prev.has_minutes else None
        )
        sleep = self.sleep_score(raw.night, base, settings) if raw.night else None
        ready = self.readiness(raw, sleep, base, prev, prev_load)
        night = raw.night
        day_key = raw.day.isoformat()
        row: dict[str, Any] = {
            "date": day_key,
            "weekday": raw.day.weekday(),
            "steps": raw.steps,
            "distance_km": raw.distance_km,
            "active_kcal": raw.active_kcal,
            "hr_avg": raw.hr_avg,
            "peak_hr": raw.peak_hr,
            "stress_avg": raw.stress_avg,
            "stress_peak_window": raw.stress_peak_window,
            "worn_hours": raw.worn_hours,
            "sources": list(raw.sources),
            "rhr": raw.rhr,
            "vitality": raw.vitality,
            "hrv": imports["hrv"].get(day_key),
            "respiratory_rate": imports["respiratory_rate"].get(day_key),
            "load": load["load"] if load else None,
            "load_points": load["points"] if load else None,
            "active_min": load["active_min"] if load else None,
            "zones": load["zones"] if load else None,
            "readiness": ready["score"] if ready else None,
            "readiness_label": ready["label"] if ready else None,
            "readiness_detail": ready,
            "load_range": list(recommended_load(ready["score"] if ready else None)),
            "baseline": {k: (_r(v) if isinstance(v, float) else v) for k, v in base.items()},
            "naps": [self.night_summary(n) for n in raw.naps],
            "nap_min": sum(n.asleep_min for n in raw.naps),
            "night": None,
        }
        if night:
            row["night"] = {**self.night_summary(night), "score": sleep["score"], "score_label": sleep["label"], "score_parts": sleep["parts"]}
        row["sleep_total_min"] = (night.asleep_min if night else 0) + row["nap_min"]
        return row

    def night_summary(self, n: Night) -> dict[str, Any]:
        return {
            "bed": clock(n.bed_ts, self.tz),
            "wake": clock(n.wake_ts, self.tz),
            "bed_ts": n.bed_ts,
            "wake_ts": n.wake_ts,
            "bed_from_noon": from_noon(n.bed_ts, self.tz),
            "wake_from_noon": from_noon(n.wake_ts, self.tz),
            "asleep_min": n.asleep_min,
            "deep_min": n.deep_min,
            "light_min": n.light_min,
            "rem_min": n.rem_min,
            "awake_min": n.awake_min,
            "awake_spells": n.awake_spells,
            "source": n.source,
            "fitbit_score": n.fitbit_score,
            "overnight": n.overnight,
        }

    # ------------------------------------------------------------ detail

    def night_detail(self, night: dict[str, Any]) -> dict[str, Any]:
        """Stages and every reading through one night (band nights only)."""
        bed, wake = night["bed_ts"], night["wake_ts"]
        stages = self.store.stages_between(bed - 3600, wake)
        segments = []
        for i, (ts, stage) in enumerate(stages):
            end = stages[i + 1][0] if i + 1 < len(stages) else wake
            a, b = max(ts, bed), min(end, wake)
            if b > a and stage in STAGES:
                if segments and segments[-1][2] == STAGES[stage] and segments[-1][0] + segments[-1][1] == (a - bed) // 60:
                    segments[-1][1] += (b - a) // 60
                else:
                    segments.append([(a - bed) // 60, max(1, (b - a) // 60), STAGES[stage]])
        readings = []
        for m in self.store.minutes_between(bed, wake):
            if m["heart_rate"] is None and m["spo2"] is None and m["stress"] is None:
                continue
            readings.append([(m["ts"] - bed) // 60, m["heart_rate"], m["spo2"], m["stress"]])
        stage_at = []
        for minute, *_ in readings:
            name = None
            for start_m, length, stage in segments:
                if start_m <= minute < start_m + length:
                    name = stage
                    break
            stage_at.append(name)
        for row, name in zip(readings, stage_at):
            row.append(name)
        return {"segments": segments, "readings": readings, "length_min": (wake - bed) // 60}

    def minutes_series(self, day: date) -> list[list[Any]]:
        """[minute of day, steps, heart rate, stress, spo2] for each band minute."""
        start, end = day_bounds(day, self.tz)
        return [
            [(m["ts"] - start) // 60, m["steps"], m["heart_rate"], m["stress"], m["spo2"]]
            for m in self.store.minutes_between(start, end)
        ]

    def hr_band(self, day: date) -> list[list[float]]:
        """Your normal heart rate by quarter hour: 10th to 90th percentile, last 30 days."""
        start, _ = day_bounds(day, self.tz)
        slots: dict[int, list[int]] = {}
        for m in self.store.minutes_between(start - BASELINE_DAYS * DAY, start):
            if m["heart_rate"] is not None:
                slots.setdefault(minute_of_day(m["ts"], self.tz) // 15, []).append(m["heart_rate"])
        out = []
        for slot in range(96):
            vals = sorted(slots.get(slot, []))
            if len(vals) >= 20:
                out.append([slot * 15, vals[len(vals) // 10], vals[(len(vals) * 9) // 10]])
        if len(out) >= 48:
            return out
        # Not enough band minutes yet: fall back to hourly averages (imported history too).
        hours: dict[int, list[float]] = {}
        for h in self.store.hourly_between(start - BASELINE_DAYS * DAY, start):
            if h["hr_n"] and h["hr_mean"] is not None:
                hours.setdefault(local(h["hour_ts"], self.tz).hour, []).append(h["hr_mean"])
        out = []
        for hour in range(24):
            vals = sorted(hours.get(hour, []))
            if len(vals) >= 5:
                lo, hi = round(vals[len(vals) // 10]), round(vals[(len(vals) * 9) // 10])
                out.extend([slot * 15, lo, hi] for slot in range(hour * 4, hour * 4 + 4))
        return out

    def hourly_series(self, day: date) -> list[dict[str, Any]]:
        start, end = day_bounds(day, self.tz)
        return [
            {
                "hour": local(h["hour_ts"], self.tz).hour,
                "steps": h["steps"] or 0,
                "hr": _r(h["hr_mean"]),
                "stress": _r(h["stress_mean"]),
                "source": h["source"] or "band",
            }
            for h in self.store.hourly_between(start, end)
        ]

    # ------------------------------------------------------------ energy

    def energy(
        self, day: date, row: dict[str, Any], prev_row: dict[str, Any] | None, max_hr: float = 185
    ) -> dict[str, Any] | None:
        """An estimate of energy (0-100) through the day, like a body battery.

        Charges while asleep (faster when overnight stress is low) and a little
        in calm awake stretches; drains with time awake, stress and activity.
        Runs minute by minute from the start of the day before.
        """
        start, end = day_bounds(day, self.tz)
        now = int(_time.time())
        stop = min(end, now)
        if stop <= start:
            return None
        sim_start = start - DAY
        minutes = {m["ts"] - m["ts"] % 60: m for m in self.store.minutes_between(sim_start, stop)}
        if not any(ts >= start for ts in minutes):
            return None
        asleep: list[tuple[int, int]] = []
        for r in (prev_row, row):
            if not r:
                continue
            for n in ([r["night"]] if r["night"] else []) + r["naps"]:
                asleep.append((n["bed_ts"], n["wake_ts"]))
        rest = row["rhr"] or (row["baseline"] or {}).get("rhr") or 60
        e = 50.0
        series: list[list[float]] = []
        factors = {"recharge": 0.0, "calm": 0.0, "stress": 0.0, "activity": 0.0, "awake": 0.0}
        wake_ts = row["night"]["wake_ts"] if row["night"] else None
        sleep_start_e = wake_e = None
        peak, peak_ts = -1.0, None
        for ts in range(sim_start, stop, 60):
            m = minutes.get(ts)
            hr = m["heart_rate"] if m else None
            st = m["stress"] if m else None
            steps = (m["steps"] or 0) if m else 0
            sleeping = any(a <= ts < b for a, b in asleep)
            counted = ts >= start or (wake_ts is not None and ts >= (row["night"]["bed_ts"]))
            if sleeping:
                q = 0.7 if st is None else clamp((45 - st) / 30, 0.2, 1.0)
                d = 0.35 * q * (100 - e) / 100
                if counted:
                    factors["recharge"] += d
            else:
                d = -0.03
                if counted:
                    factors["awake"] -= 0.03
                if st is not None:
                    if st < 20 and steps < 10 and (hr is None or hr < rest + 15):
                        c = 0.05 * (100 - e) / 100
                        d += c
                        if counted:
                            factors["calm"] += c
                    elif st > 25:
                        x = (st - 25) * 0.003
                        d -= x
                        if counted:
                            factors["stress"] -= x
                zone = hr_zone(hr, rest, max_hr) if hr is not None else 0
                if steps >= 100 and zone == 0:
                    zone = 1
                if zone:
                    x = 0.04 * zone
                    d -= x
                    if counted:
                        factors["activity"] -= x
            e = clamp(e + d, 0, 100)
            if ts >= start:
                if (ts - start) % 900 == 0:
                    series.append([(ts - start) // 60, round(e, 1)])
                if e > peak:
                    peak, peak_ts = e, ts
            if wake_ts is not None and ts == wake_ts - wake_ts % 60:
                wake_e = e
        result = {
            "now": round(e),
            "series": series,
            "peak": round(peak) if peak >= 0 else None,
            "peak_time": clock(peak_ts, self.tz),
            "at_wake": round(wake_e) if wake_e is not None else None,
            "factors": {k: round(v) for k, v in factors.items()},
            "is_today": stop == now,
        }
        return result


def readiness_summary(score: int, parts: dict[str, dict[str, Any]]) -> str:
    """One or two plain sentences: how recovered, what helped, what held it back."""
    lead = (
        "Fully recovered." if score >= 85 else "Recovered well." if score >= 70
        else "Partly recovered." if score >= 50 else "Not well recovered."
    )
    names = {"resting_hr": "Resting heart rate", "overnight_stress": "Overnight stress"}
    held_back = {
        "sleep": "a short or broken night",
        "resting_hr": "a raised resting heart rate",
        "overnight_stress": "higher overnight stress",
        "timing": "a later bedtime",
        "load": "yesterday's heavy load",
    }
    better = [
        k for k in ("resting_hr", "overnight_stress")
        if k in parts and parts[k].get("diff", 0) < 0 and parts[k]["s"] >= 0.75
    ]
    clause = None
    if len(better) == 2:
        clause = "Resting heart rate and overnight stress are both better than usual"
    elif better:
        clause = f"{names[better[0]]} is better than usual"
    elif parts.get("sleep", {}).get("s", 0) >= 0.8:
        clause = "You slept well"
    weak_key, weak = min(parts.items(), key=lambda kv: kv[1]["s"])
    if weak["s"] < 0.6:
        reason = held_back[weak_key]
        tail = f"{clause}; {reason} held the score back." if clause else f"{reason[0].upper()}{reason[1:]} held the score back."
        return f"{lead} {tail}"
    return f"{lead} {clause}." if clause else lead
