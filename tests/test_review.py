"""The daily review: the summary sent, the answer checked, and the HA round trip."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.health_hub.const import DOMAIN
from custom_components.health_hub.core.review import (
    ReviewError,
    build_prompt,
    build_summary,
    parse_review,
)
from custom_components.health_hub.core.store import IMPORT_DEVICE_ID, Store

SYDNEY = ZoneInfo("Australia/Sydney")
NOW = int(datetime(2026, 10, 27, 7, 30, tzinfo=SYDNEY).timestamp())

GOOD_ANSWER = {
    "headline": "A solid night, a little later than usual.",
    "summary": "You slept 7.2 hours. Bedtime was 40 minutes later than your typical time.",
    "observations": [
        {
            "topic": "sleep",
            "title": "Seven hours",
            "detail": "7.2 h asleep against your 14-night average of 6.8 h.",
            "level": "good",
            "based_on": "Your baseline and adult sleep guidance.",
            "sources": [
                {"title": "Sleep duration", "publisher": "AASM", "year": 2015, "url": "https://example.org/a"},
                {"title": "Not a link", "url": "javascript:alert(1)"},
            ],
        },
        {"topic": "made-up", "title": "Oxygen", "detail": "No dips below 90%.", "level": "weird"},
        {"title": "No detail"},
    ],
    "suggestions": [{"text": "Aim for lights out by 23:15.", "why": "Keeps wake time steady."}],
    "bedtime": {"suggested": "23:15", "why": "Eight hours before your usual wake."},
    "caveats": ["Stages are estimates."],
}


def _session(ts: int, hours: float, device_id: int = 1) -> dict:
    total = int(hours * 60)
    return {
        "device_id": device_id, "ts": ts, "wakeup_ts": ts + total * 60 + 300, "is_awake": 0,
        "total_min": total, "deep_min": total // 4, "light_min": total // 2,
        "rem_min": total // 5, "awake_min": 5,
    }


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "hub.db")
    yield s
    s.close()


def _fill(store: Store) -> None:
    sleeps = []
    for days_ago in range(0, 10):
        bed = NOW - days_ago * 86400 - 8 * 3600  # about 23:30 the night before
        sleeps.append(_session(bed, 7.0 + days_ago % 3 * 0.5))
    sleeps.append(_session(NOW - 86400 + 6 * 3600, 0.5))  # yesterday's afternoon nap
    sleeps.append(_session(NOW - 8 * 3600 + 600, 8.0, IMPORT_DEVICE_ID))  # Fitbit, same night
    store.ingest("sleep_session", sleeps)
    bed = NOW - 8 * 3600
    minutes = []
    for m in range(0, 7 * 60):
        minutes.append({
            "device_id": 1, "ts": bed + m * 60, "steps": 0, "heart_rate": 58 + m % 7,
            "stress": 12 + m % 5, "spo2": 88 if m == 100 else (96 if m % 10 == 0 else None),
        })
    for m in range(0, 600):  # yesterday daytime
        minutes.append({
            "device_id": 1, "ts": NOW - 86400 + 2 * 3600 + m * 60, "steps": 10,
            "heart_rate": 80, "stress": 30, "spo2": None,
        })
    store.ingest("minute", minutes)


def test_summary_figures(store):
    _fill(store)
    s = build_summary(store, SYDNEY, NOW)
    night = s["last_night"]
    assert night["source"] == "band"  # the band's beats the imported Fitbit night
    assert night["asleep_hours"] == 7.0
    assert night["overnight"]["heart_rate_lowest"] == 58
    assert night["overnight"]["spo2_lowest"] == 88
    assert night["overnight"]["spo2_readings_below_90"] == 1
    assert [n["asleep_hours"] for n in s["naps_since_yesterday"]] == [0.5]
    prev = s["previous_14_nights"]
    assert prev["nights_recorded"] == 9
    assert prev["typical_bedtime"] == "23:30"
    assert prev["overnight_stress_average"] is None  # no minute data for those nights
    assert s["activity"]["yesterday"]["steps"] == 6000
    assert s["activity"]["yesterday"]["worn_hours"] == 10.5  # incl. 23:30-midnight in bed
    assert s["weight"] is None and s["fitbit_history"] is None


def test_summary_has_no_identifying_detail(store):
    _fill(store)
    store.upsert_devices([{"device_id": 1, "name": "Nick's band", "manufacturer": "Xiaomi",
                           "type_name": "MI_BAND8_PRO", "model": "M2333B1"}])
    text = build_prompt(build_summary(store, SYDNEY, NOW))
    assert "Nick" not in text and "M2333B1" not in text
    assert '"date": "2026-10-27"' in text


def test_parse_keeps_good_parts():
    review = parse_review(GOOD_ANSWER)
    assert review["headline"].startswith("A solid night")
    assert len(review["observations"]) == 2
    first, second = review["observations"]
    assert [x["url"] for x in first["sources"]] == ["https://example.org/a"]
    assert (second["topic"], second["level"]) == ("data", "neutral")
    assert review["bedtime"]["suggested"] == "23:15"
    assert review["attention"] == 1  # worst level is neutral


@pytest.mark.parametrize("answer", [None, [], {}, {"observations": [{"title": "x"}]}])
def test_parse_rejects_empty(answer):
    with pytest.raises(ReviewError):
        parse_review(answer)


def test_parse_drops_bad_bedtime():
    review = parse_review({**GOOD_ANSWER, "bedtime": {"suggested": "late"}})
    assert review["bedtime"] is None


# ------------------------------------------------------------ Home Assistant


@pytest.fixture
async def hub_entry(recorder_mock, enable_custom_integrations, hass: HomeAssistant, tmp_path):
    hass.config.config_dir = str(tmp_path)
    await hass.config.async_set_time_zone("Australia/Sydney")
    entry = MockConfigEntry(domain=DOMAIN, title="Health Hub", data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _review_dir(hass: HomeAssistant) -> Path:
    return Path(hass.config.path("health_hub/review"))


def _answer(hass: HomeAssistant, review_id: str, **extra) -> None:
    d = _review_dir(hass)
    (d / "status.json").write_text(json.dumps({"alive": "now", "state": "idle", "logged_in": True}))
    body = {"id": review_id, "status": "ok", "review": GOOD_ANSWER, "cost_usd": 0.1, **extra}
    (d / "response.json").write_text(json.dumps(body))
    later = time.time() + 5  # a newer file than any seen before
    os.utime(d / "response.json", (later, later))


async def _poll(hass: HomeAssistant) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_review_round_trip(hub_entry, hass: HomeAssistant, hass_ws_client):
    assert hass.states.get("sensor.health_hub_reviewer").state == "not_installed"
    await hass.services.async_call(DOMAIN, "request_review", blocking=True)
    request = json.loads((_review_dir(hass) / "request.json").read_text())
    assert request["reason"] == "manual"
    assert "## Summary" in request["prompt"]

    _answer(hass, request["id"])
    await _poll(hass)

    state = hass.states.get("sensor.health_hub_daily_review")
    assert state.state == GOOD_ANSWER["headline"]
    assert state.attributes["attention"] == "neutral"
    assert hass.states.get("sensor.health_hub_reviewer").state == "ready"
    assert not (_review_dir(hass) / "request.json").exists()

    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "health_hub/review", "history": True})
    msg = await ws.receive_json()
    assert msg["success"], msg
    latest = msg["result"]["latest"]
    assert latest["status"] == "ok" and latest["meta"]["cost_usd"] == 0.1
    assert latest["summary"]["date"] == request["day"]
    assert msg["result"]["history"][0]["headline"] == GOOD_ANSWER["headline"]


async def test_unusable_answer_is_an_error(hub_entry, hass: HomeAssistant):
    await hass.services.async_call(DOMAIN, "request_review", blocking=True)
    request = json.loads((_review_dir(hass) / "request.json").read_text())
    d = _review_dir(hass)
    (d / "response.json").write_text(json.dumps({"id": request["id"], "status": "ok", "review": {}}))
    await _poll(hass)
    reviews = hub_entry.runtime_data.reviews
    assert reviews.last_attempt["status"] == "error"
    assert "could not be used" in reviews.last_attempt["error"]
    assert hass.states.get("sensor.health_hub_daily_review").state == "unknown"


async def test_morning_review_after_sleep_syncs(hub_entry, hass: HomeAssistant):
    hub = hub_entry.runtime_data
    wake = int(dt_util.start_of_local_day().timestamp()) + 60
    session = _session(wake - 7 * 3600 - 300, 7.0)
    await hass.async_add_executor_job(hub.store.ingest, "sleep_session", [session])
    hub.on_sleep_synced()
    await hass.async_block_till_done()
    assert not (_review_dir(hass) / "request.json").exists()  # waits for the rest of the sync

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=11))
    await hass.async_block_till_done(wait_background_tasks=True)
    request = json.loads((_review_dir(hass) / "request.json").read_text())
    assert request["reason"] == "morning"

    hub.on_sleep_synced()  # a later sync the same day doesn't ask again
    await hass.async_block_till_done()
    assert hub.reviews._settle is None


async def test_review_can_be_turned_off(hub_entry, hass: HomeAssistant):
    hass.config_entries.async_update_entry(hub_entry, options={"review_enabled": False})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.health_hub_reviewer").state == "disabled"
