"""Longevity: long-term habits against published guidance.

A report card, not another detail page. Each area (heart, movement, sleep)
rates a few figures over the last 90 days against cited guidance, compares
them with the 90 days before and shows the last 12 months. The detail lives
on the existing pages; this links to them.

Pure Python: no Home Assistant imports.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from itertools import pairwise
from typing import Any

from . import fitness as fit
from .metrics import Calculator, RawDay, from_noon
from .settings import Settings
from .store import Store

WINDOW = 90  # days in "now" and in "before"
MONTHS = 12
MIN_DAYS = 14  # fewest days with data before a 90-day figure is shown
SRI_DAYS = 30  # regularity is worked out over the last 30 days
SRI_MIN_PAIRS = 7
EPOCH = 300  # seconds per sleep/wake epoch for regularity
WORN_MIN_H = 10  # a day counts for active minutes if the band was on this long
STEP_DAY_MIN = 500  # a day with fewer steps is treated as not worn

GOOD, FAIR, LOW = "good", "fair", "low"
ORDER = {GOOD: 0, FAIR: 1, LOW: 2}


# ------------------------------------------------------------------ helpers


def _months(today: date) -> list[str]:
    out = []
    y, m = today.year, today.month
    for _ in range(MONTHS):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _r(v: float | None, n: int = 0) -> float | int | None:
    if v is None:
        return None
    return round(v, n) if n else round(v)


def _trend(now: float | None, before: float | None, better: str, steady: float) -> dict[str, Any] | None:
    if now is None or before is None:
        return None
    change = now - before
    if abs(change) < steady:
        direction = "steady"
    elif (change < 0) == (better == "lower"):
        direction = "better"
    else:
        direction = "worse"
    return {"before": before, "change": change, "direction": direction}


def _worst(ratings: list[str | None]) -> str | None:
    known = [r for r in ratings if r]
    return max(known, key=lambda r: ORDER[r]) if known else None


# ------------------------------------------------------------------- report


class Longevity:
    def __init__(self, calc: Calculator, store: Store, settings: Settings, today: date) -> None:
        self.calc = calc
        self.store = store
        self.settings = settings
        self.today = today
        self.last = today - timedelta(days=1)  # whole days only
        first = today.replace(day=1)
        for _ in range(MONTHS - 1):
            first = (first - timedelta(days=1)).replace(day=1)
        self.first = min(first, self.last - timedelta(days=2 * WINDOW - 1))
        span = (self.last - self.first).days + 1
        self.raws: list[RawDay] = [calc.raw(self.first + timedelta(days=i)) for i in range(span)]
        self.months = _months(today)
        rhrs = [r.rhr for r in self.raws[-WINDOW:] if r.rhr]
        self.usual_rest = _median(rhrs) or 60
        self._epoch_cache: dict[date, list[int]] = {}

    # windows: 0 = the last 90 days, 1 = the 90 days before
    def _window(self, which: int) -> list[RawDay]:
        end = len(self.raws) - which * WINDOW
        return self.raws[max(0, end - WINDOW):end]

    def _monthly(self, value: Callable[[list[RawDay]], float | None]) -> list[list[Any]]:
        by: dict[str, list[RawDay]] = {m: [] for m in self.months}
        for r in self.raws:
            key = r.day.strftime("%Y-%m")
            if key in by:
                by[key].append(r)
        return [[m, value(days) if days else None] for m, days in by.items()]

    # ------------------------------------------------------------- heart

    def resting_hr(self) -> dict[str, Any]:
        def fig(days: list[RawDay]) -> float | None:
            vals = [r.rhr for r in days if r.rhr]
            return _median(vals) if len(vals) >= MIN_DAYS else None

        def month(days: list[RawDay]) -> float | None:
            vals = [r.rhr for r in days if r.rhr]
            return _r(_median(vals), 1) if len(vals) >= 5 else None

        now, before = fig(self._window(0)), fig(self._window(1))
        rating = None if now is None else GOOD if now < 60 else FAIR if now <= 80 else LOW
        return {
            "key": "resting_hr",
            "label": "Resting heart rate",
            "value": _r(now, 1),
            "unit": "bpm",
            "summary": "median of the last 3 months",
            "rating": rating,
            "target": "Under 60 bpm",
            "trend": _trend(now, before, "lower", 1),
            "better": "lower",
            "monthly": self._monthly(month),
            "rule": "Rated against a meta-analysis of 46 studies: compared with the lowest group, a resting rate of 60–80 bpm carried a slightly higher risk of death from any cause and above 80 a clearly higher one, rising by about 9% for every 10 bpm. Under 60 is rated on track, 60–80 fair and above 80 needs attention.",
            "note": "A lower resting heart rate generally goes with better fitness.",
            "sources": ["resting_hr_mortality", "resting_hr"],
        }

    def heart(self) -> dict[str, Any]:
        rhr = self.resting_hr()
        if rhr["rating"] is None:
            action = "Wear the band overnight: resting heart rate needs a couple of weeks of nights."
        elif rhr["trend"] and rhr["trend"]["direction"] == "worse":
            action = f"Up {abs(rhr['trend']['change']):.1f} bpm on the 3 months before. The Movement targets below are the habits that work on it."
        elif rhr["rating"] == GOOD:
            action = "Nothing to change here: keep the movement habits that got you here."
        else:
            action = "The Movement targets below are the habits that work on it; check back on the trend in a month."
        return {"key": "heart", "title": "Heart", "page": "heart", "metrics": [rhr], "action": action}

    # ----------------------------------------------------------- fitness

    def cardio_fitness(self) -> dict[str, Any]:
        st = self.settings
        tests = fit.walk_tests(self.store, self.calc.tz, st.sex, st.age)
        scored = [t for t in tests if t["vo2max"] is not None]
        latest = scored[-1] if scored else None
        prev = scored[-2] if len(scored) > 1 else None
        rating = fit.rate(st.sex, st.age, latest["vo2max"]) if latest and st.sex and st.age else None
        ref = fit.reference_for(st.sex, st.age) if st.sex and st.age else None
        rough = fit.ratio_range(st.effective_max_hr, _median([r.rhr for r in self._window(0) if r.rhr]))
        monthly: dict[str, float] = {}
        for t in scored:
            monthly[t["date"][:7]] = t["vo2max"]
        if latest:
            fa = latest["fitness_age"]
            age_text = f"{'under ' if fa['bound'] == 'under' else 'over ' if fa['bound'] == 'over' else ''}{fa['age']}"
            d = date.fromisoformat(latest["date"])
            summary = f"1-mile walk test on {d.day} {d.strftime('%b %Y')} · fitness age {age_text}"
        elif tests and not (st.sex and st.age):
            summary = "set your sex and age in Settings to score your walk test"
        else:
            summary = "do the 1-mile walk test below"
        trend = None
        if latest and prev:
            trend = _trend(latest["vo2max"], prev["vo2max"], "higher", 1.0)
        return {
            "key": "cardio_fitness",
            "label": "Cardio fitness (VO2max)",
            "value": latest["vo2max"] if latest else None,
            "unit": "mL/kg/min",
            "summary": summary,
            "rating": rating,
            "target": f"{ref['mean']:g}+ (average for healthy {'men' if st.sex == 'male' else 'women'} {ref['from']}–{ref['to'] if ref['to'] < 90 else '+'})" if ref else "set your sex and age in Settings",
            "goal": ref["mean"] if ref else None,
            "trend": trend,
            "trend_label": "vs your previous test",
            "better": "higher",
            "detail": {
                "fitness_age": latest["fitness_age"] if latest else None,
                "rough_range": rough,
                "last_test_days": (self.today - date.fromisoformat(latest["date"])).days if latest else None,
            },
            "monthly": [[m, monthly.get(m)] for m in self.months],
            "rule": (
                "VO2max is the most oxygen your body can use at full effort, the usual measure of cardio fitness. It's estimated "
                "from a 1-mile walk done as fast as you can (the Rockport walk test: your weight, age, sex, time and heart rate at "
                "the finish, worked out from treadmill tests of 343 adults aged 30–69). It's compared with treadmill tests of 3,816 healthy "
                "Norwegian adults: at or above the average for your sex and age group is on track, within one standard deviation "
                "below it fair, and lower needs attention (Health Hub's own bands). Fitness age is the age at which healthy people "
                "of your sex in that study average your figure. In a follow-up of 37,000 Norwegian adults over 24 years, higher "
                "estimated fitness went with lower risk of death in those under 60."
            ),
            "note": (
                f"For comparison, a rough figure from your heart rates alone (maximum ÷ resting × 12 to 15.3) is "
                f"{rough[0]:g}–{rough[1]:g}; it's only a guide, as the multiplier varies a lot between people."
                if rough else None
            ),
            "sources": ["fitness_reference"],
            "why_sources": ["rockport_walk", "fitness_reference", "fitness_mortality", "hr_ratio", "hr_ratio_general"],
        }

    def fitness(self) -> dict[str, Any]:
        m = self.cardio_fitness()
        d = m["detail"]
        if m["value"] is None:
            action = "Do the 1-mile walk test below: about 15 minutes on flat ground. Repeat it every couple of months to see the trend."
        elif d["last_test_days"] is not None and d["last_test_days"] > 90:
            action = f"Your last walk test was {d['last_test_days']} days ago: repeat it to see where you are now."
        elif m["rating"] == GOOD:
            action = "Above average for your age. Repeat the walk test every couple of months to keep track."
        else:
            action = "Meeting the Movement targets, including some vigorous minutes, is the way to raise it; repeat the test in 8 weeks."
        return {"key": "fitness", "title": "Cardio fitness", "page": None, "metrics": [m], "action": action, "walk_test": True}

    # ---------------------------------------------------------- movement

    def steps(self) -> dict[str, Any]:
        older = (self.settings.age or 0) >= 60
        plateau = 6000 if older else 8000

        def fig(days: list[RawDay], need: int = MIN_DAYS) -> float | None:
            vals = [r.steps for r in days if r.steps >= STEP_DAY_MIN]
            return _mean(vals) if len(vals) >= need else None

        now, before = fig(self._window(0)), fig(self._window(1))
        rating = None if now is None else GOOD if now >= plateau else FAIR if now >= plateau - 2000 else LOW
        return {
            "key": "steps",
            "label": "Daily steps",
            "value": _r(now),
            "unit": "a day",
            "summary": "average of the last 3 months",
            "rating": rating,
            "target": f"{plateau:,}+ a day",
            "goal": plateau,
            "trend": _trend(now, before, "higher", max(250, (before or 0) * 0.05)),
            "better": "higher",
            "monthly": self._monthly(lambda d: _r(fig(d, 5))),
            "rule": (
                f"Across 15 cohorts, the risk of dying from any cause fell with more steps a day until it levelled off at "
                f"{'6,000–8,000 for adults 60 and over' if older else '8,000–10,000 for adults under 60'}. "
                f"{plateau:,} or more is rated on track, within 2,000 of it fair (Health Hub's own rule), and less needs attention. "
                f"Days with fewer than {STEP_DAY_MIN} steps are left out as days the band wasn't worn."
            ),
            "sources": ["steps_mortality"],
        }

    def _active(self, r: RawDay) -> tuple[int, int] | None:
        """(moderate-or-harder minutes, vigorous minutes) for one day, if worn enough."""
        if not r.has_minutes or (r.worn_hours or 0) < WORN_MIN_H:
            return None
        rest = r.rhr or self.usual_rest
        reserve = max(self.settings.effective_max_hr - rest, 40)
        moderate_hr = rest + 0.4 * reserve
        vigorous_hr = rest + 0.6 * reserve
        mod = sum(n for hr, n in r.hr_hist.items() if hr >= moderate_hr)
        mod += sum(n for hr, n in r.brisk_hist.items() if hr < moderate_hr)
        vig = sum(n for hr, n in r.hr_hist.items() if hr >= vigorous_hr)
        return mod, vig

    def active_minutes(self) -> dict[str, Any]:
        def weekly(days: list[RawDay], need: int = MIN_DAYS) -> tuple[float, float] | None:
            per = [a for a in (self._active(r) for r in days) if a]
            if len(per) < need:
                return None
            mod = sum(a[0] for a in per) / len(per) * 7
            vig = sum(a[1] for a in per) / len(per) * 7
            return mod, vig

        def equivalent(w: tuple[float, float] | None) -> float | None:
            # WHO: 150 moderate or 75 vigorous, or an equivalent mix, so a vigorous minute counts twice.
            return None if w is None else w[0] + w[1]

        now_w, before_w = weekly(self._window(0)), weekly(self._window(1))
        now, before = equivalent(now_w), equivalent(before_w)
        rating = None if now is None else GOOD if now >= 150 else FAIR if now >= 75 else LOW
        days_counted = sum(1 for r in self._window(0) if self._active(r))
        return {
            "key": "active_minutes",
            "label": "Moderate or harder activity",
            "value": _r(now),
            "unit": "min a week",
            "summary": f"average week, from {days_counted} days with all-day heart rate" if now is not None else "needs two weeks of all-day wear",
            "rating": rating,
            "target": "150–300 min a week",
            "goal": 150,
            "trend": _trend(now, before, "higher", max(10, (before or 0) * 0.1)),
            "better": "higher",
            "detail": {"vigorous": _r(now_w[1]) if now_w else None},
            "monthly": self._monthly(lambda d: _r(equivalent(weekly(d, 5)))),
            "rule": (
                "WHO recommends 150–300 minutes of moderate activity a week, or 75–150 of vigorous, or a mix; every minute counts, "
                "with no minimum length. A minute counts as moderate if you took 100 or more steps in it, or your heart rate was at "
                "least 40% of the way from resting to maximum; vigorous from 60%. Vigorous minutes count double. 150 or more is on "
                "track, 75–149 fair (Health Hub's own halfway mark), less needs attention."
            ),
            "note": f"Only days the band was worn at least {WORN_MIN_H} hours are counted. Heart rate raised by stress or heat can count too.",
            "sources": ["who_activity", "cadence_moderate", "relative_intensity"],
        }

    def strength(self) -> dict[str, Any]:
        logs = self.store.training_between((self.first - timedelta(days=1)).isoformat(), self.last.isoformat())
        gym_days = sorted({x["day"] for x in logs if x["kind"] == "gym"})
        first_log = gym_days[0] if gym_days else None

        def per_week(start: date, end: date) -> float | None:
            if first_log is None or end.isoformat() < first_log:
                return None
            start = max(start, date.fromisoformat(first_log))
            days = (end - start).days + 1
            if days < 7:
                return None
            n = sum(1 for d in gym_days if start.isoformat() <= d <= end.isoformat())
            return n / days * 7

        w0s = self.last - timedelta(days=WINDOW - 1)
        now = per_week(w0s, self.last)
        before = per_week(w0s - timedelta(days=WINDOW), w0s - timedelta(days=1))
        rating = None if now is None else GOOD if now >= 2 else FAIR if now >= 1 else LOW
        monthly = []
        for m in self.months:
            y, mo = map(int, m.split("-"))
            start = date(y, mo, 1)
            end = (date(y + (mo == 12), mo % 12 + 1, 1) - timedelta(days=1))
            end = min(end, self.last)
            monthly.append([m, _r(per_week(start, end), 1) if end >= start else None])
        return {
            "key": "strength",
            "label": "Strength training",
            "value": _r(now, 1),
            "unit": "days a week",
            "summary": "gym days logged on Training, last 3 months" if now is not None else "log gym sessions on Training",
            "rating": rating,
            "target": "2+ days a week",
            "goal": 2,
            "trend": _trend(now, before, "higher", 0.25),
            "better": "higher",
            "monthly": monthly,
            "rule": "WHO recommends muscle-strengthening activity that works all the major muscle groups on 2 or more days a week. Days with a gym session logged on the Training page are counted, from your first logged session. 2 or more is on track, 1 fair, less needs attention.",
            "sources": ["who_activity"],
        }

    def movement(self) -> dict[str, Any]:
        steps, active, strength = self.steps(), self.active_minutes(), self.strength()
        action = None
        if active["rating"] in (LOW, FAIR):
            gap = 150 - active["value"]
            walks = max(1, -(-gap // 20))
            action = f"Add about {gap} minutes a week to reach 150: {walks} brisk 20-minute walk{'s' if walks > 1 else ''} (100+ steps a minute) would do it."
        elif strength["rating"] in (LOW, FAIR):
            action = "Add a gym day: WHO counts days, so aim for sessions on 2 different days each week."
        elif steps["rating"] in (LOW, FAIR):
            gap = steps["goal"] - steps["value"]
            action = f"About {gap:,} more steps a day reaches {steps['goal']:,}: roughly {max(5, round(gap / 100 / 5) * 5)} minutes' walking."
        elif strength["rating"] is None:
            action = "Log your gym sessions on the Training page so strength training can be rated."
        elif all(m["rating"] == GOOD for m in (steps, active, strength)):
            action = "On track on all three. Keep it up."
        return {"key": "movement", "title": "Movement", "page": "activity", "metrics": [steps, active, strength], "action": action}

    # ------------------------------------------------------------- sleep

    def duration(self) -> dict[str, Any]:
        def fig(days: list[RawDay], need: int = MIN_DAYS) -> float | None:
            vals = [r.night.asleep_min for r in days if r.night]
            return _mean(vals) if len(vals) >= need else None

        now, before = fig(self._window(0)), fig(self._window(1))
        rating = None if now is None else GOOD if now >= 420 else FAIR if now >= 360 else LOW
        return {
            "key": "sleep_duration",
            "label": "Time asleep",
            "value": _r(now),
            "unit": "min",
            "format": "duration",
            "summary": "average night asleep, last 3 months",
            "rating": rating,
            "target": "7 h or more",
            "goal": 420,
            "trend": _trend(now, before, "higher", 10),
            "better": "higher",
            "monthly": self._monthly(lambda d: _r(fig(d, 5))),
            "rule": "The American Academy of Sleep Medicine and Sleep Research Society recommend 7 hours or more a night for adults. 7 h or more of time asleep is on track, 6–7 h fair, less needs attention.",
            "sources": ["aasm_sleep_duration"],
        }

    def _epochs(self, day: date) -> list[int]:
        """Timestamps every 5 minutes on the local clock from noon the day before."""
        cached = self._epoch_cache.get(day)
        if cached is None:
            start = datetime.combine(day - timedelta(days=1), time(12), self.calc.tz)
            cached = [int((start + timedelta(seconds=i * EPOCH)).timestamp()) for i in range(86400 // EPOCH)]
            self._epoch_cache[day] = cached
        return cached

    def _sri(self, days: list[RawDay]) -> tuple[float, int] | None:
        """Sleep Regularity Index over pairs of consecutive days that both have a night."""
        slept: set[int] = set()
        for r in days:
            for n in ([r.night] if r.night else []) + list(r.naps):
                slept.update(range(-(-n.bed_ts // EPOCH), -(-n.wake_ts // EPOCH)))
        if not slept:
            return None

        def asleep(ts: int) -> bool:
            return ts // EPOCH in slept

        agree = total = pairs = 0
        for a, b in pairwise(days):
            if not (a.night and b.night) or (b.day - a.day).days != 1:
                continue
            # Each night's block runs from noon the day before, compared moment by
            # moment on the local clock, so a change of daylight saving isn't a shift.
            pairs += 1
            for ta, tb in zip(self._epochs(a.day), self._epochs(b.day)):
                agree += asleep(ta) == asleep(tb)
                total += 1
        if pairs < SRI_MIN_PAIRS:
            return None
        return 200 * agree / total - 100, pairs

    def regularity(self) -> dict[str, Any]:
        recent = self.raws[-SRI_DAYS:]
        earlier = self.raws[-2 * SRI_DAYS:-SRI_DAYS]
        now_p, before_p = self._sri(recent), self._sri(earlier)
        now = now_p[0] if now_p else None
        before = before_p[0] if before_p else None
        rating = None if now is None else GOOD if now >= 81 else FAIR if now >= 73.8 else LOW
        monthly = []
        for m in self.months:
            days = [r for r in self.raws if r.day.strftime("%Y-%m") == m]
            v = self._sri(days) if len(days) >= SRI_MIN_PAIRS + 1 else None
            monthly.append([m, _r(v[0]) if v else None])
        wakes = [r.night.wake_ts for r in recent if r.night]
        spread = None
        if len(wakes) >= SRI_MIN_PAIRS:
            spread = _r(statistics.pstdev(from_noon(w, self.calc.tz) for w in wakes))
        return {
            "key": "sleep_regularity",
            "label": "Sleep regularity",
            "value": _r(now),
            "unit": "of 100",
            "summary": f"Sleep Regularity Index, last {SRI_DAYS} days ({now_p[1]} pairs of nights)" if now_p else f"needs {SRI_MIN_PAIRS} pairs of consecutive nights",
            "rating": rating,
            "target": "81 or more",
            "goal": 81,
            "trend": _trend(now, before, "higher", 3),
            "trend_label": "vs the 30 days before",
            "better": "higher",
            "detail": {"wake_spread_min": spread},
            "monthly": monthly,
            "rule": (
                "The Sleep Regularity Index is the chance of being in the same state, asleep or awake, at any two moments 24 hours "
                "apart, scaled so 100 is perfectly regular. In 60,977 UK Biobank adults, more regular sleepers had a 20–48% lower "
                "risk of death than the least regular fifth; half scored 81 or more and the middle half ran from 73.8 to 86.3. "
                "81 or more is on track, 73.8–81 fair, below 73.8 needs attention."
            ),
            "note": "Worked out from your bed and wake times (and naps) in 5-minute steps; time awake in the night isn't subtracted, so your score may read a little higher than the study's.",
            "sources": ["sleep_regularity"],
        }

    def sleep(self) -> dict[str, Any]:
        dur, reg = self.duration(), self.regularity()
        action = None
        if dur["rating"] in (LOW, FAIR):
            gap = 420 - dur["value"]
            action = f"Averaging {dur['value'] // 60} h {dur['value'] % 60:02d} m asleep: getting to bed about {max(5, round(gap / 5) * 5)} minutes earlier would reach 7 h (your target is in bed by {self.settings.bed_target})."
        elif reg["rating"] in (LOW, FAIR):
            spread = reg["detail"]["wake_spread_min"]
            action = (f"Your wake time varies by about ±{spread} minutes. " if spread else "") + "Getting up at the same time every day, weekends included, is the most direct way to raise regularity."
        elif dur["rating"] == GOOD and reg["rating"] == GOOD:
            action = "Long enough and regular. Keep it up."
        return {"key": "sleep", "title": "Sleep", "page": "sleep", "metrics": [dur, reg], "action": action}

    # ------------------------------------------------------------ report

    def report(self) -> dict[str, Any]:
        areas = [self.heart(), self.fitness(), self.movement(), self.sleep()]
        for a in areas:
            a["rating"] = _worst([m["rating"] for m in a["metrics"]])
            for m in a["metrics"]:
                t = m.get("trend")
                if t:
                    t["before"] = _r(t["before"], 1)
                    t["change"] = _r(t["change"], 1)
        rated = [m for a in areas for m in a["metrics"] if m["rating"]]
        st = self.settings
        tests = fit.walk_tests(self.store, self.calc.tz, st.sex, st.age)
        weights = self.store.measurements("weight")
        return {
            "walk_tests": tests[::-1],
            "walk_test_ready": {
                "sex": st.sex is not None,
                "age": st.age is not None,
                "weight": bool(weights) and weights[-1]["ts"] >= int(datetime.combine(self.today, time(0), self.calc.tz).timestamp()) - fit.WEIGHT_MAX_AGE_DAYS * 86400,
            },
            "as_of": self.last.isoformat(),
            "months": self.months,
            "areas": areas,
            "counts": {r: sum(1 for m in rated if m["rating"] == r) for r in (GOOD, FAIR, LOW)},
            "rated": len(rated),
            "total": sum(len(a["metrics"]) for a in areas),
        }


def longevity_view(calc: Calculator, store: Store, settings: Settings, today: date) -> dict[str, Any]:
    return Longevity(calc, store, settings, today).report()
