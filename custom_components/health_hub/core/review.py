"""The daily review: what Claude is told, what it is asked, and checking its answer.

`build_summary` turns the store into a small set of figures (nightly and daily
totals, averages and baselines). Only these figures leave Home Assistant: no
minute-by-minute readings, names, devices or locations.

`build_prompt` wraps the summary in the instructions, and `parse_review`
checks the answer against the expected shape, dropping anything malformed.

Pure Python: no Home Assistant imports.
"""

from __future__ import annotations

import json
import statistics
from datetime import date, datetime, timedelta, tzinfo
from typing import Any

from .store import IMPORT_DEVICE_ID, Store

SUMMARY_VERSION = 1
MAIN_SLEEP_MIN = 180  # a sleep this long or longer is a night, not a nap
DAY = 86400

LEVELS = ("good", "neutral", "watch", "see_doctor")
TOPICS = ("sleep", "heart", "oxygen", "stress", "activity", "weight", "recovery", "data")


class ReviewError(ValueError):
    """The answer could not be used."""


# --------------------------------------------------------------------- helpers


def _r(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(float(value), digits)


def _hours(minutes: float | None) -> float | None:
    return None if minutes is None else round(minutes / 60, 2)


def _clock(ts: int, tz: tzinfo) -> str:
    return datetime.fromtimestamp(ts, tz).strftime("%H:%M")


def _minutes_from_noon(ts: int, tz: tzinfo) -> int:
    """Clock time as minutes after midday, so bedtimes either side of midnight sort."""
    t = datetime.fromtimestamp(ts, tz)
    return (t.hour * 60 + t.minute - 720) % 1440


def _clock_from_noon(minutes: float) -> str:
    m = int(round(minutes + 720)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def sleeps_by_day(store: Store, tz: tzinfo, since_ts: int) -> dict[date, list[dict[str, Any]]]:
    """Sleep sessions by the day they ended; the band's beat imported ones."""
    found: dict[date, dict[bool, list[dict[str, Any]]]] = {}
    for s in store.sleep_sessions_since(since_ts - DAY):
        end = s["wakeup_ts"] or s["ts"]
        if end < since_ts:
            continue
        day = datetime.fromtimestamp(end, tz).date()
        found.setdefault(day, {True: [], False: []})[s["device_id"] != IMPORT_DEVICE_ID].append(dict(s))
    return {d: v[True] or v[False] for d, v in found.items()}


def main_sleep(sessions: list[dict[str, Any]]) -> dict[str, Any] | None:
    longest = max(sessions, key=lambda s: s["total_min"] or 0, default=None)
    if longest and (longest["total_min"] or 0) >= MAIN_SLEEP_MIN:
        return longest
    return None


def _session(s: dict[str, Any], tz: tzinfo) -> dict[str, Any]:
    total = s["total_min"] or 0
    out: dict[str, Any] = {
        "fell_asleep": _clock(s["ts"], tz),
        "woke": _clock(s["wakeup_ts"], tz) if s["wakeup_ts"] else None,
        "asleep_hours": _hours(total),
        "deep_hours": _hours(s["deep_min"]),
        "light_hours": _hours(s["light_min"]),
        "rem_hours": _hours(s["rem_min"]),
        "awake_in_bed_hours": _hours(s["awake_min"]),
        "source": "band" if s["device_id"] != IMPORT_DEVICE_ID else "imported",
    }
    if s.get("score") is not None:
        out["score"] = s["score"]
    if total:
        for stage in ("deep", "rem"):
            if s[f"{stage}_min"] is not None:
                out[f"{stage}_percent"] = round(100 * s[f"{stage}_min"] / total)
    return out


def _night_readings(store: Store, s: dict[str, Any]) -> dict[str, Any] | None:
    if not s["wakeup_ts"] or s["device_id"] == IMPORT_DEVICE_ID:
        return None
    w = store.window_stats(s["ts"], s["wakeup_ts"])
    if not (w["hr_n"] or w["stress_n"] or w["spo2_n"]):
        return None
    return {
        "heart_rate_lowest": w["hr_min"],
        "heart_rate_average": _r(w["hr_avg"]),
        "stress_average": _r(w["stress_avg"]),
        "spo2_average": _r(w["spo2_avg"]),
        "spo2_lowest": w["spo2_min"],
        "spo2_readings": w["spo2_n"],
        "spo2_readings_below_90": w["spo2_below_90"],
    }


def _daily_activity(store: Store, tz: tzinfo, start_ts: int) -> dict[date, dict[str, Any]]:
    """Per local day from the hourly table: steps, calories, stress and wear time."""
    days: dict[date, dict[str, Any]] = {}
    for h in store.hourly_since(start_ts):
        d = days.setdefault(
            datetime.fromtimestamp(h["hour_ts"], tz).date(),
            {"steps": 0, "active_kcal": 0, "stress_sum": 0.0, "stress_n": 0, "worn_hours": 0,
             "sources": set()},
        )
        d["sources"].add("band" if (h["source"] or "band") == "band" else "imported")
        d["steps"] += h["steps"] or 0
        d["active_kcal"] += h["active_calories"] or 0
        if h["stress_n"] and h["stress_mean"] is not None:
            d["stress_sum"] += h["stress_mean"] * h["stress_n"]
            d["stress_n"] += h["stress_n"]
        if h["hr_n"] and (h["source"] or "band") == "band":
            d["worn_hours"] += min(h["hr_n"], 60) / 60
    out = {}
    for day, d in days.items():
        out[day] = {
            "steps": d["steps"],
            "active_kcal": d["active_kcal"],
            "stress_average": _r(d["stress_sum"] / d["stress_n"]) if d["stress_n"] else None,
            "worn_hours": _r(d["worn_hours"]) if "band" in d["sources"] else None,
            "source": "+".join(sorted(d["sources"])),
        }
    return out


def _resting(store: Store, tz: tzinfo, since: date) -> dict[date, float]:
    values: dict[date, float] = {}
    for day, value in store.daily_metric("resting_heart_rate"):
        d = date.fromisoformat(day)
        if d >= since:
            values[d] = value
    for row in store.daily_since(int(datetime.combine(since, datetime.min.time(), tz).timestamp()) - DAY):
        d = datetime.fromtimestamp(row["ts"], tz).date()
        if d >= since and row["hr_resting"] is not None:
            values[d] = row["hr_resting"]  # the band's beat imported values
    return values


# ---------------------------------------------------------------------- summary


def build_summary(
    store: Store, tz: tzinfo, now_ts: int, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The figures Claude reviews. Small, rounded and free of identifying detail."""
    now = datetime.fromtimestamp(now_ts, tz)
    today = now.date()
    since_30 = today - timedelta(days=30)
    start_30 = int(datetime.combine(since_30, datetime.min.time(), tz).timestamp())

    summary: dict[str, Any] = {
        "summary_version": SUMMARY_VERSION,
        "date": today.isoformat(),
        "weekday": now.strftime("%A"),
        "local_time": now.strftime("%H:%M"),
        "device": "Xiaomi Smart Band 8 Pro (wrist), read with Gadgetbridge",
    }

    # Sleep ---------------------------------------------------------------
    by_day = sleeps_by_day(store, tz, start_30)
    tonight = by_day.get(today, [])
    night = main_sleep(tonight)
    if night:
        last = _session(night, tz)
        readings = _night_readings(store, night)
        if readings:
            last["overnight"] = readings
        summary["last_night"] = last
    else:
        summary["last_night"] = None
    naps = [s for s in by_day.get(today - timedelta(days=1), []) if (s["total_min"] or 0) < MAIN_SLEEP_MIN]
    naps += [s for s in tonight if s is not night and (s["total_min"] or 0) < MAIN_SLEEP_MIN]
    summary["naps_since_yesterday"] = [_session(s, tz) for s in naps]

    nights = []
    for offset in range(1, 15):
        s = main_sleep(by_day.get(today - timedelta(days=offset), []))
        if s:
            nights.append(s)
    if nights:
        totals = [n["total_min"] / 60 for n in nights if n["total_min"]]
        beds = [_minutes_from_noon(n["ts"], tz) for n in nights]
        wakes = [_minutes_from_noon(n["wakeup_ts"], tz) for n in nights if n["wakeup_ts"]]
        deep = [100 * n["deep_min"] / n["total_min"] for n in nights if n["deep_min"] is not None and n["total_min"]]
        rem = [100 * n["rem_min"] / n["total_min"] for n in nights if n["rem_min"] is not None and n["total_min"]]
        overnight = [r for r in (_night_readings(store, n) for n in nights) if r]
        summary["previous_14_nights"] = {
            "nights_recorded": len(nights),
            "asleep_hours_average": _r(_mean(totals), 2),
            "asleep_hours_shortest": _r(min(totals), 2) if totals else None,
            "asleep_hours_longest": _r(max(totals), 2) if totals else None,
            "typical_bedtime": _clock_from_noon(statistics.median(beds)),
            "typical_wake": _clock_from_noon(statistics.median(wakes)) if wakes else None,
            "bedtime_variation_minutes": round(statistics.pstdev(beds)) if len(beds) > 1 else None,
            "deep_percent_average": round(_mean(deep)) if deep else None,
            "rem_percent_average": round(_mean(rem)) if rem else None,
            "overnight_stress_average": _r(_mean([r["stress_average"] for r in overnight if r["stress_average"] is not None])),
            "overnight_lowest_heart_rate_average": _r(_mean([r["heart_rate_lowest"] for r in overnight if r["heart_rate_lowest"] is not None])),
            "overnight_spo2_average": _r(_mean([r["spo2_average"] for r in overnight if r["spo2_average"] is not None])),
        }
    else:
        summary["previous_14_nights"] = None

    # Resting heart rate --------------------------------------------------
    resting = _resting(store, tz, since_30)
    if resting:
        latest_day = max(resting)
        recent = [v for d, v in resting.items() if d > today - timedelta(days=7)]
        summary["resting_heart_rate"] = {
            "latest": {"date": latest_day.isoformat(), "bpm": resting[latest_day]},
            "average_7_days": _r(_mean(recent)),
            "average_30_days": _r(_mean(list(resting.values()))),
            "days_recorded_30": len(resting),
        }
    else:
        summary["resting_heart_rate"] = None

    # Activity ------------------------------------------------------------
    activity = _daily_activity(store, tz, start_30)
    yesterday = today - timedelta(days=1)
    full_days = {d: v for d, v in activity.items() if d < today}
    summary["activity"] = {
        "today_so_far": activity.get(today),
        "yesterday": activity.get(yesterday),
        "last_7_days": [
            {"date": d.isoformat(), **activity[d]}
            for d in sorted(full_days)
            if d >= today - timedelta(days=7)
        ],
        "steps_average_30_days": round(_mean([v["steps"] for v in full_days.values()]))
        if full_days
        else None,
        "days_recorded_30": len(full_days),
    }

    # Old Fitbit figures, as context -------------------------------------
    fitbit: dict[str, Any] = {}
    for metric, label in (("hrv", "hrv_ms"), ("respiratory_rate", "breaths_per_minute")):
        series = store.daily_metric(metric)
        if series:
            last30 = [v for _d, v in series[-30:]]
            fitbit[metric] = {
                "last_recorded": series[-1][0],
                f"last_value_{label}": _r(series[-1][1]),
                f"average_of_last_30_records_{label}": _r(_mean(last30)),
            }
    summary["fitbit_history"] = fitbit or None

    # Weight --------------------------------------------------------------
    weights = store.measurement_series("weight")
    if weights:
        ts, kg = weights[-1]
        month_ago = [v for t, v in weights if t <= ts - 30 * DAY]
        summary["weight"] = {
            "latest_kg": _r(kg),
            "latest_date": datetime.fromtimestamp(ts, tz).date().isoformat(),
            "change_30_days_kg": _r(kg - month_ago[-1]) if month_ago else None,
        }
    else:
        summary["weight"] = None

    if extra:
        summary.update(extra)
    return summary


def has_enough_data(summary: dict[str, Any]) -> bool:
    return bool(
        summary.get("last_night")
        or summary.get("previous_14_nights")
        or (summary.get("activity") or {}).get("days_recorded_30")
    )


# ----------------------------------------------------------------------- prompt

ANSWER_SHAPE = {
    "headline": "One calm sentence, at most 90 characters.",
    "summary": "Two to four sentences on the night and the day ahead.",
    "observations": [
        {
            "topic": "one of: " + ", ".join(TOPICS),
            "title": "A few words.",
            "detail": "One to three sentences, with the numbers it rests on.",
            "level": "one of: " + ", ".join(LEVELS),
            "based_on": "What it is compared with: the owner's baseline, a guideline, or both.",
            "sources": [{"title": "Page title", "publisher": "Organisation or journal", "year": 2024, "url": "https://..."}],
        }
    ],
    "suggestions": [
        {"text": "Something concrete to do today.", "why": "One sentence.", "sources": ["same shape as above"]}
    ],
    "bedtime": {"suggested": "HH:MM or null", "why": "One sentence."},
    "caveats": ["Anything the owner should know about the data's limits today."],
}

PROMPT = """You are writing the morning review for a personal health dashboard in Home \
Assistant. One adult reads it: the person the data is about. Nothing else is known \
about them (age, sex, medical history, medication), so say so when a judgement \
depends on those.

## About the data
The summary at the end was computed from a Xiaomi Smart Band 8 Pro worn on the \
wrist, read with Gadgetbridge.
- Times are local. "last_night" is the main sleep that ended today; naps are listed \
separately and count towards total sleep.
- Sleep times and stages are the band's estimates, not a sleep study.
- "stress" is the band's 1-100 score, which the maker derives from heart-rate \
variability. The band does not export HRV itself, so overnight stress stands in for \
overnight HRV here: lower stress roughly means higher HRV.
- SpO2 is a wrist optical reading. Single low readings are often movement or fit \
artefacts; judge patterns, not one reading.
- "fitbit_history" comes from the owner's previous Fitbit. It may overlap the \
band's first weeks, and it is background, not today's data. Days marked source \
"imported" also come from the Fitbit; "worn_hours" is only known for band days.
- Missing values (null) mean no data, not zero.

## How to write it
1. Compare with the owner's own recent figures first (the 7, 14 and 30 day \
averages), then with population guidance.
2. Check each health statement against current, reputable evidence using web \
search, opening the pages where you can: clinical guidelines, major health bodies \
and peer-reviewed research, preferably from the last ten years. Cite the sources \
you relied on, with links taken from the pages or search results you saw; never \
write a link from memory. If you could not verify something, leave it out.
3. Do not diagnose. If the data shows a pattern that is worth raising with a \
doctor, say so plainly, use level "see_doctor" and explain why. Do not reassure \
without evidence either: anything called normal must say compared with what.
4. Use only numbers from the summary. If there is too little data to judge \
(for example only a few nights so far), say that instead of guessing.
5. Keep it short, calm and practical: two to five observations, at most three \
suggestions, each something that can be done today.
6. If there is a last night, suggest a bedtime for tonight with a reason, \
otherwise set "bedtime" to null.

## Answer
Reply with a single JSON object and nothing else, in this shape:
{shape}

## Summary
```json
{summary}
```
"""


def build_prompt(summary: dict[str, Any]) -> str:
    return PROMPT.format(
        shape=json.dumps(ANSWER_SHAPE, indent=2),
        summary=json.dumps(summary, indent=2),
    )


# --------------------------------------------------------------- the answer


def _text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value[:limit] if value else None


def _sources(value: Any) -> list[dict[str, Any]]:
    out = []
    for s in value if isinstance(value, list) else []:
        if not isinstance(s, dict):
            continue
        url = _text(s.get("url"), 500)
        if not url or not url.startswith(("https://", "http://")):
            continue
        year = s.get("year")
        out.append(
            {
                "title": _text(s.get("title"), 200) or url,
                "publisher": _text(s.get("publisher"), 120),
                "year": year if isinstance(year, int) and 1900 < year < 2100 else None,
                "url": url,
            }
        )
    return out[:6]


def parse_review(answer: Any) -> dict[str, Any]:
    """Keep the well-formed parts of Claude's answer. Raises ReviewError if nothing is usable."""
    if not isinstance(answer, dict):
        raise ReviewError("the answer is not a JSON object")
    observations = []
    for o in answer.get("observations") or []:
        if not isinstance(o, dict):
            continue
        detail = _text(o.get("detail"), 800)
        title = _text(o.get("title"), 80)
        if not (detail and title):
            continue
        topic = o.get("topic") if o.get("topic") in TOPICS else "data"
        level = o.get("level") if o.get("level") in LEVELS else "neutral"
        observations.append(
            {
                "topic": topic,
                "title": title,
                "detail": detail,
                "level": level,
                "based_on": _text(o.get("based_on"), 300),
                "sources": _sources(o.get("sources")),
            }
        )
    suggestions = []
    for s in answer.get("suggestions") or []:
        if isinstance(s, dict) and _text(s.get("text"), 300):
            suggestions.append(
                {
                    "text": _text(s.get("text"), 300),
                    "why": _text(s.get("why"), 400),
                    "sources": _sources(s.get("sources")),
                }
            )
    bedtime = None
    b = answer.get("bedtime")
    if isinstance(b, dict) and isinstance(b.get("suggested"), str):
        try:
            datetime.strptime(b["suggested"].strip(), "%H:%M")
        except ValueError:
            pass
        else:
            bedtime = {"suggested": b["suggested"].strip(), "why": _text(b.get("why"), 400)}
    headline = _text(answer.get("headline"), 120)
    summary = _text(answer.get("summary"), 1200)
    if not (headline or summary or observations):
        raise ReviewError("the answer has no headline, summary or observations")
    return {
        "headline": headline or (observations[0]["title"] if observations else summary[:120]),
        "summary": summary,
        "observations": observations[:8],
        "suggestions": suggestions[:5],
        "bedtime": bedtime,
        "caveats": [c for c in (_text(c, 300) for c in answer.get("caveats") or []) if c][:5],
        "attention": max(
            (LEVELS.index(o["level"]) for o in observations), default=1
        ),
    }


def attention_label(review: dict[str, Any]) -> str:
    return LEVELS[review.get("attention", 1)]
