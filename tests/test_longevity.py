"""Longevity: ratings, trends and the Sleep Regularity Index."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.health_hub.core import settings as settings_mod
from custom_components.health_hub.core import training
from custom_components.health_hub.core.longevity import Longevity, longevity_view
from custom_components.health_hub.core.metrics import Night, RawDay
from custom_components.health_hub.core.store import Store

TZ = ZoneInfo("Australia/Sydney")
TODAY = date(2026, 10, 27)


class FakeCalc:
    """Hands out RawDays made by a function of the day."""

    tz = TZ

    def __init__(self, make):
        self.make = make

    def raw(self, day):
        return self.make(day)


def _night(day, bed="22:30", wake="06:30", shift_min=0):
    t = time.fromisoformat(bed)
    b = datetime.combine(day - timedelta(days=0 if t.hour < 12 else 1), t, TZ) + timedelta(minutes=shift_min)
    w = datetime.combine(day, time.fromisoformat(wake), TZ) + timedelta(minutes=shift_min)
    return Night(day=day, bed_ts=int(b.timestamp()), wake_ts=int(w.timestamp()), asleep_min=int((w - b).total_seconds() // 60),
                 deep_min=None, light_min=None, rem_min=None, awake_min=None, source="band", fitbit_score=None)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "hub.db")
    yield s
    s.close()


def _report(store, make, **settings):
    if settings:
        settings_mod.update(store, settings)
    return longevity_view(FakeCalc(make), store, settings_mod.load(store), TODAY)


def _metric(report, key):
    return next(m for a in report["areas"] for m in a["metrics"] if m["key"] == key)


def test_ratings_and_trends(store):
    recent = TODAY - timedelta(days=90)

    def make(day):
        new = day >= recent
        return RawDay(day=day, steps=9000 if new else 6500, rhr=58 if new else 64, night=_night(day) if new else _night(day, bed="00:00"))

    r = _report(store, make, age=38)
    steps, rhr, sleep = _metric(r, "steps"), _metric(r, "resting_hr"), _metric(r, "sleep_duration")
    assert steps["value"] == 9000 and steps["rating"] == "good"
    assert steps["trend"]["direction"] == "better" and steps["trend"]["change"] == 2500
    assert rhr["value"] == 58 and rhr["rating"] == "good" and rhr["trend"]["direction"] == "better"
    assert sleep["value"] == 480 and sleep["rating"] == "good"
    assert sleep["trend"]["before"] == 390  # midnight to 06:30
    assert len(rhr["monthly"]) == 12 and rhr["monthly"][-1][0] == "2026-10"


def test_thresholds(store):
    r = _report(store, lambda d: RawDay(day=d, steps=6500, rhr=82, night=_night(d, bed="00:30")))
    assert _metric(r, "steps")["rating"] == "fair"  # within 2,000 of 8,000
    assert _metric(r, "resting_hr")["rating"] == "low"
    assert _metric(r, "sleep_duration")["rating"] == "fair"  # 6 h
    heart = next(a for a in r["areas"] if a["key"] == "heart")
    assert heart["rating"] == "low"


def test_older_adults_plateau_earlier(store):
    r = _report(store, lambda d: RawDay(day=d, steps=6500), age=65)
    assert _metric(r, "steps")["rating"] == "good"


def test_unworn_days_are_left_out(store):
    r = _report(store, lambda d: RawDay(day=d, steps=9000 if d.day % 2 else 100))
    assert _metric(r, "steps")["value"] == 9000


def test_regular_sleep_scores_100_and_shifting_sleep_less(store):
    regular = _report(store, lambda d: RawDay(day=d, night=_night(d)))
    assert _metric(regular, "sleep_regularity")["value"] == 100
    assert _metric(regular, "sleep_regularity")["rating"] == "good"
    # Every other night two hours later.
    shifted = _report(store, lambda d: RawDay(day=d, night=_night(d, shift_min=120 if d.toordinal() % 2 else 0)))
    sri = _metric(shifted, "sleep_regularity")
    # 4 of 24 hours disagree on every pair: 200 * 20/24 - 100 = 66.7
    assert sri["value"] == 67 and sri["rating"] == "low"
    assert sri["detail"]["wake_spread_min"] == 60
    sleep = next(a for a in shifted["areas"] if a["key"] == "sleep")
    assert "same time every day" in sleep["action"]


def test_regularity_needs_consecutive_nights(store):
    r = _report(store, lambda d: RawDay(day=d, night=_night(d) if d.toordinal() % 2 else None))
    assert _metric(r, "sleep_regularity")["value"] is None


def test_active_minutes_count_brisk_and_vigorous(store):
    # Rest 60, max 180: moderate from 108 bpm, vigorous from 132.
    def make(day):
        return RawDay(day=day, rhr=60, has_minutes=True, worn_hours=16,
                      hr_hist={70: 900, 115: 10, 140: 5}, brisk_hist={95: 6})

    r = _report(store, make, max_hr=180)
    m = _metric(r, "active_minutes")
    # (10 + 5 + 6 brisk) moderate-or-harder + 5 vigorous counted again = 26 a day
    assert m["value"] == 26 * 7 and m["rating"] == "good"
    assert m["detail"]["vigorous"] == 35


def test_short_wear_days_dont_count(store):
    r = _report(store, lambda d: RawDay(day=d, has_minutes=True, worn_hours=4, hr_hist={150: 60}))
    assert _metric(r, "active_minutes")["value"] is None


def test_strength_days_from_training_log(store):
    start = TODAY - timedelta(days=28)
    for i in range(0, 28, 7):
        training.log(store, start + timedelta(days=i), "gym", "push")
        training.log(store, start + timedelta(days=i), "gym", "pull")  # same day counts once
        training.log(store, start + timedelta(days=i + 3), "gym", "legs")
    training.log(store, start + timedelta(days=1), "compex", None)
    r = _report(store, lambda d: RawDay(day=d))
    m = _metric(r, "strength")
    assert m["value"] == 2.0 and m["rating"] == "good"


def test_no_data_is_not_rated(store):
    r = _report(store, lambda d: RawDay(day=d))
    assert r["rated"] == 0 and all(a["rating"] is None for a in r["areas"])
    assert r["total"] == 6


def test_settings_sex_and_height(store):
    s = settings_mod.update(store, {"sex": "Female", "height_cm": 171.4})
    assert s.sex == "female" and s.height_cm == 171
    with pytest.raises(settings_mod.SettingsError):
        settings_mod.update(store, {"sex": "other"})
    with pytest.raises(settings_mod.SettingsError):
        settings_mod.update(store, {"height_cm": 20})
    assert settings_mod.update(store, {"sex": None}).sex is None


def test_report_uses_whole_days(store):
    seen = []
    Longevity(FakeCalc(lambda d: seen.append(d) or RawDay(day=d)), store, settings_mod.load(store), TODAY)
    assert max(seen) == TODAY - timedelta(days=1)
    assert min(seen) <= date(2025, 11, 1)
