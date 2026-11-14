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
    assert r["total"] == 7


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


# ------------------------------------------------------------- fitness

from custom_components.health_hub.core import fitness


def test_rockport_equation():
    # 30-year-old man, 180 lb, 12:15, finish 165 bpm: 47.88 in published worked examples.
    assert fitness.rockport(180 / fitness.LB_PER_KG, 30, True, 12.25, 165) == pytest.approx(47.88, abs=0.05)


def test_fitness_age_and_rating():
    assert fitness.fitness_age("male", 49.1) == {"age": 35, "bound": None}
    assert fitness.fitness_age("male", 45.0)["age"] == 50  # between 47.2 (45) and 42.6 (55)
    assert fitness.fitness_age("male", 60) == {"age": 25, "bound": "under"}
    assert fitness.fitness_age("female", 20)["bound"] == "over"
    assert fitness.rate("male", 38, 50) == "good"
    assert fitness.rate("male", 38, 43) == "fair"  # within one SD (7.5) of 49.1
    assert fitness.rate("male", 38, 40) == "low"
    assert fitness.ratio_range(180, 60) == [36.0, 45.9]


def _ts(day, hhmm):
    return fitness.finish_ts(day, hhmm, TZ)


def test_walk_test_needs_weight_then_scores(store):
    day = TODAY - timedelta(days=3)
    finish = _ts(day, "07:30")
    with pytest.raises(fitness.FitnessError, match="weigh-in"):
        fitness.log_walk_test(store, finish, 13 * 60, 150)
    store.add_measurement(finish - 5 * 86400, "weight", 82.0)
    fitness.log_walk_test(store, finish, 13 * 60 + 30, 150)
    tests = fitness.walk_tests(store, TZ, "male", 38)
    assert len(tests) == 1 and tests[0]["hr_from"] == "manual"
    expect = fitness.rockport(82.0, 38 - 3 / 365.25, True, 13.5, 150)
    assert tests[0]["vo2max"] == round(expect, 1)

    r = _report(store, lambda d: RawDay(day=d, rhr=60), sex="male", age=38)
    m = _metric(r, "cardio_fitness")
    assert m["value"] == tests[0]["vo2max"] and m["rating"] is not None
    assert m["detail"]["fitness_age"] == tests[0]["fitness_age"]
    assert r["walk_tests"][0]["ts"] == finish and r["walk_test_ready"]["weight"]

    assert fitness.delete_walk_test(store, finish)
    assert fitness.walk_tests(store, TZ, "male", 38) == []


def test_walk_test_uses_band_heart_rate(store):
    day = TODAY - timedelta(days=1)
    finish = _ts(day, "18:05")
    store.add_measurement(finish, "weight", 80.0)
    with pytest.raises(fitness.FitnessError, match="no heart rate"):
        fitness.log_walk_test(store, finish, 900, None)
    with store._lock, store._db:
        for i, hr in enumerate((138, 146, 141)):
            store._db.execute("INSERT INTO minute_samples (device_id, ts, heart_rate) VALUES (1, ?, ?)", (finish - 60 + i * 60, hr))
    logged = fitness.log_walk_test(store, finish, 900, None)
    assert logged["hr"] == 146 and logged["hr_from"] == "band"
    assert fitness.walk_tests(store, TZ, "male", 38)[0]["hr_from"] == "band"


def test_walk_test_checks_inputs(store):
    with pytest.raises(fitness.FitnessError):
        fitness.log_walk_test(store, _ts(TODAY, "00:01"), 100, 150)
    with pytest.raises(fitness.FitnessError, match="future"):
        fitness.finish_ts(date.today() + timedelta(days=2), "08:00", TZ)
    with pytest.raises(fitness.FitnessError):
        fitness.finish_ts(TODAY, "soon", TZ)


def test_no_walk_test_shows_rough_range(store):
    r = _report(store, lambda d: RawDay(day=d, rhr=60), sex="male", age=38, max_hr=180)
    m = _metric(r, "cardio_fitness")
    assert m["value"] is None and m["detail"]["rough_range"] == [36.0, 45.9]
    assert "walk test" in next(a for a in r["areas"] if a["key"] == "fitness")["action"]
