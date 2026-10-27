"""Highlights: short statements worked out from the owner's own figures.

Each rule fires only when its condition holds, and returns its numbers and
the rule itself so the page can show them under "Why?". Sources are keys
into `sources.py`. Nothing here is fixed text about health.

Pure Python: no Home Assistant imports.
"""

from __future__ import annotations

import statistics
from typing import Any

from .settings import Settings


def _clock(minutes_from_noon: float) -> str:
    m = int(round(minutes_from_noon + 720)) % 1440
    h, mm = divmod(m, 60)
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}:{mm:02d}{suffix}"


def _dur(minutes: float) -> str:
    minutes = int(round(minutes))
    h, m = divmod(abs(minutes), 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def _mean(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.fmean(vals) if vals else None


def insight(key: str, tone: str, icon: str, title: str, text: str, rule: str,
            numbers: str, sources: list[str] | None = None, note: str | None = None) -> dict[str, Any]:
    return {
        "id": key, "tone": tone, "icon": icon, "title": title, "text": text,
        "why": {"rule": rule, "numbers": numbers, "sources": sources or [], "note": note},
    }


# ----------------------------------------------------------- overview rules


def resting_hr_trend(days: list[dict[str, Any]]) -> dict[str, Any] | None:
    """days: the last 37 days, oldest first; today last."""
    rhr = [d["rhr"] for d in days]
    week = [v for v in rhr[-7:] if v is not None]
    month = [v for v in rhr[-37:-7] if v is not None]
    if len(week) < 4 or len(month) < 10:
        return None
    w, m = statistics.fmean(week), statistics.fmean(month)
    diff = w - m
    if abs(diff) < 2:
        return None
    latest = next((v for v in reversed(rhr) if v is not None), None)
    down = diff < 0
    return insight(
        "resting_hr_trend", "good" if down else "watch", "trend-down" if down else "trend-up",
        f"Resting heart rate is trending {'down' if down else 'up'}.",
        f"{round(latest)} bpm today; this week's average is {abs(diff):.0f} {'below' if down else 'above'} the 30 days before.",
        "Shown when your 7-day average resting heart rate is 2 bpm or more away from your average over the 30 days before.",
        f"Last 7 days: {w:.0f} bpm · 30 days before: {m:.0f} bpm.",
        ["resting_hr"],
        "A rise of a few beats can come with poor sleep, illness, alcohol or stress; a fall often with better fitness or recovery."
        if not down else None,
    )


def bedtime_drift(days: list[dict[str, Any]], settings: Settings) -> dict[str, Any] | None:
    beds = [d["night"]["bed_from_noon"] if d["night"] else None for d in days]
    week = [b for b in beds[-7:] if b is not None]
    last = [b for b in beds[-14:-7] if b is not None]
    if len(week) < 4:
        return None
    w = statistics.fmean(week)
    target = (settings.bed_minutes - 720) % 1440
    vs_last = w - statistics.fmean(last) if len(last) >= 4 else None
    vs_target = w - target
    if (vs_last is not None and vs_last >= 30) or vs_target >= 30:
        parts = []
        if vs_last is not None and vs_last >= 30:
            parts.append(f"{_dur(vs_last)} later than last week")
        if vs_target >= 30:
            parts.append(f"{_dur(vs_target)} past your target")
        return insight(
            "bedtime_drift", "watch", "moon", "Bedtimes are drifting later.",
            f"Average {_clock(w)} this week, " + " and ".join(parts) + ".",
            "Shown when this week's average time you fell asleep is 30 minutes or more later than last week's, or than your bedtime target.",
            f"This week {_clock(w)}"
            + (f" · last week {_clock(statistics.fmean(last))}" if len(last) >= 4 else "")
            + f" · target {_clock(target)}.",
            ["sleep_regularity"],
            "In a large UK Biobank study, people with more regular sleep times had a lower risk of death, separately from how long they slept. It shows a link, not proof of cause.",
        )
    if vs_last is not None and vs_last <= -30:
        return insight(
            "bedtime_earlier", "good", "moon", "Earlier nights this week.",
            f"Average {_clock(w)}, {_dur(-vs_last)} earlier than last week.",
            "Shown when this week's average time you fell asleep is 30 minutes or more earlier than last week's.",
            f"This week {_clock(w)} · last week {_clock(statistics.fmean(last))}.",
        )
    return None


def stress_peak(days: list[dict[str, Any]]) -> dict[str, Any] | None:
    windows = [d["stress_peak_window"] for d in days[-7:] if d["stress_peak_window"] is not None]
    if len(windows) < 4:
        return None
    top, count = statistics.multimode(windows)[0], windows.count(statistics.multimode(windows)[0])
    if count < 4:
        return None
    start = top * 2

    def hr(h: int) -> str:
        return f"{h % 12 or 12}{'am' if h < 12 or h == 24 else 'pm'}"

    label = "Afternoons" if 12 <= start < 18 else "Mornings" if 6 <= start < 12 else "Evenings" if start >= 18 else "Nights"
    return insight(
        "stress_peak", "info", "clock", f"{label} are your stress peak.",
        f"{count} of the last {len(windows)} days had their highest stress between {hr(start)} and {hr(start + 2)}.",
        "Shown when the same two-hour window held the day's highest average stress on 4 or more of the last 7 days. Stress is the band's own 1–100 score.",
        f"{count} of {len(windows)} days with readings.",
    )


def steps_vs_usual(days: list[dict[str, Any]], settings: Settings) -> dict[str, Any] | None:
    full = days[:-1]  # today isn't finished
    week = [d["steps"] for d in full[-7:] if d["steps"]]
    month = [d["steps"] for d in full[-37:-7] if d["steps"]]
    if len(week) < 5 or len(month) < 10:
        return None
    w, m = statistics.fmean(week), statistics.fmean(month)
    change = (w - m) / m
    if abs(change) < 0.2:
        return None
    up = change > 0
    return insight(
        "steps_trend", "good" if up else "watch", "trend-up" if up else "trend-down",
        f"{'More' if up else 'Fewer'} steps this week.",
        f"{w:,.0f} a day over the last 7 days, {abs(change):.0%} {'above' if up else 'below'} the 30 days before.",
        "Shown when your average daily steps over the last 7 full days differ by 20% or more from the 30 days before.",
        f"Last 7 days: {w:,.0f} · 30 days before: {m:,.0f} · goal {settings.steps_goal:,}.",
        ["steps_mortality"],
        "Across 15 studies, more daily steps were linked to lower risk of death, levelling off at about 6,000 to 8,000 a day for adults 60 and over and 8,000 to 10,000 for younger adults.",
    )


def sleep_debt_high(debt_min: int, settings: Settings) -> dict[str, Any] | None:
    if debt_min < 90:
        return None
    return insight(
        "sleep_debt", "watch", "moon", "Sleep debt is building.",
        f"{_dur(debt_min)} short of your goal over the last 7 days.",
        "Shown when the last 7 days' sleep, naps included, falls 90 minutes or more short of your nightly goal in total.",
        f"Goal {_dur(settings.sleep_goal_min)} a night · short by {_dur(debt_min)} this week.",
        ["aasm_sleep_duration"],
        "Adults are advised to sleep 7 hours or more a night regularly.",
    )


def overview_highlights(days: list[dict[str, Any]], settings: Settings, debt_min: int) -> list[dict[str, Any]]:
    found = [
        resting_hr_trend(days),
        bedtime_drift(days, settings),
        sleep_debt_high(debt_min, settings),
        stress_peak(days),
        steps_vs_usual(days, settings),
    ]
    return [f for f in found if f][:3]


# --------------------------------------------------------------- sleep rules


def weekend_deep(days: list[dict[str, Any]]) -> dict[str, Any] | None:
    nights = [(d["weekday"], d["night"]["deep_min"]) for d in days[-28:] if d["night"] and d["night"]["deep_min"] is not None]
    # A night is credited to the morning you woke; Saturday and Sunday mornings follow weekend nights.
    weekend = [v for wd, v in nights if wd in (5, 6)]
    weekday = [v for wd, v in nights if wd not in (5, 6)]
    if len(weekend) < 3 or len(weekday) < 8:
        return None
    a, b = statistics.fmean(weekend), statistics.fmean(weekday)
    if abs(a - b) < 15:
        return None
    more = a > b
    return insight(
        "weekend_deep", "info", "trend-up" if more else "trend-down",
        f"{'More' if more else 'Less'} deep sleep on weekends.",
        f"Weekend mornings averaged {_dur(a)} of deep sleep, {_dur(abs(a - b))} {'more' if more else 'less'} than weekdays.",
        "Compares Saturday and Sunday mornings with the rest over the last 4 weeks. Shown when the gap is 15 minutes or more. Stages are the band's estimates.",
        f"{len(weekend)} weekend and {len(weekday)} weekday nights.",
    )


def early_nights(days: list[dict[str, Any]], settings: Settings) -> dict[str, Any] | None:
    target = (settings.bed_minutes + 15 - 720) % 1440
    early, late = [], []
    for d in days[-28:]:
        if d["night"] and d["readiness"] is not None:
            (early if d["night"]["bed_from_noon"] <= target else late).append(d["readiness"])
    if len(early) < 5 or len(late) < 5:
        return None
    gap = statistics.fmean(early) - statistics.fmean(late)
    if gap < 5:
        return None
    return insight(
        "early_nights", "good", "clock", "Earlier nights help.",
        f"After nights asleep by {_clock(target)}, readiness the next morning averaged {gap:.0f} points higher.",
        "Compares mornings after nights asleep by your bedtime target (plus 15 minutes) with the rest, over the last 4 weeks. Shown when the gap is 5 points or more and each group has at least 5 nights.",
        f"{len(early)} earlier and {len(late)} later nights.",
        note="A pattern in your own data, not proof of cause.",
    )


def oxygen_rule(night: dict[str, Any] | None, baseline_spo2: float | None) -> dict[str, Any] | None:
    o = (night or {}).get("overnight")
    if not o or not o.get("spo2_n"):
        return None
    below = o["spo2_below_90"]
    drop = (baseline_spo2 - o["spo2_avg"]) if baseline_spo2 is not None and o["spo2_avg"] is not None else None
    flagged = below >= 3 or (drop is not None and drop >= 2)
    parts = [f"{o['spo2_n']} readings, average {o['spo2_avg']:.0f}%, lowest {o['spo2_min']}%"]
    parts.append(f"{below} below 90%")
    if baseline_spo2 is not None:
        parts.append(f"your usual average {baseline_spo2:.0f}%")
    return {
        "flagged": flagged,
        "title": "Oxygen: worth keeping an eye on" if flagged else "Oxygen: not flagged",
        "text": "; ".join(parts) + ".",
        "why": {
            "rule": "Flagged when 3 or more readings in a night are below 90%, or the night's average is 2 points or more below your usual.",
            "numbers": "; ".join(parts) + ".",
            "note": "Sleep clinics measure time spent below 90% oxygen as a sign of low oxygen at night, which has been linked to high blood pressure. Wrist readings are approximate, so a flag is a prompt to watch for a pattern or ask a doctor, not a diagnosis.",
            "sources": ["spo2_t90"],
        },
    }


def sleep_highlights(days: list[dict[str, Any]], settings: Settings) -> list[dict[str, Any]]:
    return [f for f in (weekend_deep(days), early_nights(days, settings), bedtime_drift(days, settings)) if f][:3]
