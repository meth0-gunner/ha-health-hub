"""Tests for the Home Assistant-independent core."""

from __future__ import annotations

import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from custom_components.health_hub.core import gadgetbridge as gb
from custom_components.health_hub.core.protocol import (
    MAX_ROWS_PER_BATCH,
    ProtocolError,
    build_plan,
    parse_batch,
)
from custom_components.health_hub.core.stats import (
    STATS_BY_KEY,
    rows_for_change,
    sum_rows,
)
from custom_components.health_hub.core.store import Store

from .gbfixture import DAY0, make_export

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import sync_export  # noqa: E402

SYDNEY = ZoneInfo("Australia/Sydney")
MINUTE = gb.TABLES_BY_NAME["XIAOMI_ACTIVITY_SAMPLE"]


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "hub.db")
    yield s
    s.close()


def _sync(store: Store, export: Path, overlap_hours: int = 48, max_rows: int | None = None):
    def get_plan():
        plan = build_plan(store, overlap_hours)
        if max_rows:
            plan["max_rows"] = max_rows
        return plan

    def post(payload):
        batch = parse_batch(payload)
        store.upsert_devices(batch.devices)
        store.ingest(batch.spec.kind, batch.rows)
        store.advance_cursor(batch.spec.name, batch.max_ts, batch.raw_count)
        return {"accepted": len(batch.rows)}

    return sync_export.sync(str(export), get_plan, post)


def test_no_reading_becomes_missing():
    row = gb.normalise_row(
        MINUTE,
        {"TIMESTAMP": 100, "DEVICE_ID": 1, "STEPS": -1, "HEART_RATE": 0,
         "STRESS": 255, "SPO2": 0, "DISTANCE_CM": 0, "ACTIVE_CALORIES": 0},
    )
    assert row["heart_rate"] is None
    assert row["stress"] is None
    assert row["spo2"] is None
    assert row["steps"] == 0


def test_unit_detected_from_value():
    assert gb.to_seconds(1792996800, gb.UNIT_MS) == 1792996800
    assert gb.to_seconds(1792996800123, gb.UNIT_S) == 1792996800


def test_millisecond_tables_and_timezone():
    spec = gb.TABLES_BY_NAME["XIAOMI_DAILY_SUMMARY_SAMPLE"]
    row = gb.normalise_row(spec, {"TIMESTAMP": DAY0 * 1000, "TIMEZONE": 44, "HR_RESTING": 58})
    assert row["ts"] == DAY0
    assert row["tz_offset_min"] == 660
    assert row["hr_resting"] == 58


def test_full_sync_from_export(store, tmp_path):
    export = make_export(tmp_path / "Gadgetbridge", minutes=180)
    sent = _sync(store, export)
    assert sent["XIAOMI_ACTIVITY_SAMPLE"] == 180
    assert sent["BASE_ACTIVITY_SUMMARY"] == 1

    totals = store.totals_between(DAY0, DAY0 + 86400)
    assert totals["steps"] == 162 * 20  # 18 of 180 minutes had no data
    hourly = store.hourly_since(0)
    assert len(hourly) == 3
    assert hourly[0]["hr_n"] == 54 and hourly[0]["hr_min"] == 70
    assert store.latest_value("battery") == (DAY0 + 8 * 3600, 87)
    assert store.latest_row("sleep_sessions")["total_min"] == 480


def test_no_private_fields_leave_the_phone(tmp_path):
    export = make_export(tmp_path / "Gadgetbridge", minutes=5)
    seen: list[dict] = []

    class Empty:
        def get_cursor(self, _name):
            return None

    sync_export.sync(str(export), lambda: build_plan(Empty(), 48), lambda b: seen.append(b) or {})
    sent_columns = {c for b in seen for c in b["columns"]}
    sent_device_keys = {k for b in seen for d in b["devices"] for k in d}
    for private in ("BASE_LATITUDE", "BASE_LONGITUDE", "GPX_TRACK", "RAW_SUMMARY_DATA", "BIRTHDAY"):
        assert private not in sent_columns
    assert "IDENTIFIER" not in sent_device_keys  # Bluetooth address stays on the phone
    assert not any(b["table"] == "USER" for b in seen)


def test_resync_is_idempotent_and_cursor_overlaps(store, tmp_path):
    export = make_export(tmp_path / "Gadgetbridge", minutes=120)
    _sync(store, export)
    first = [dict(r) for r in store.hourly_since(0)]
    sent = _sync(store, export)
    # The overlap means recent rows are re-sent; totals must not double.
    assert sent["XIAOMI_ACTIVITY_SAMPLE"] == 120
    assert [dict(r) for r in store.hourly_since(0)] == first
    plan = build_plan(store, overlap_hours=0)
    minute = next(t for t in plan["tables"] if t["name"] == MINUTE.name)
    assert minute["since"] == DAY0 + 7 * 3600 + 119 * 60


def test_paging_with_small_batches(store, tmp_path):
    export = make_export(tmp_path / "Gadgetbridge", minutes=250)
    sent = _sync(store, export, max_rows=37)
    assert sent["XIAOMI_ACTIVITY_SAMPLE"] == 250
    assert store.totals_between(0, 2**40)["minutes"] == 250


def test_purge_keeps_hourly_history(store, tmp_path):
    _sync(store, make_export(tmp_path / "Gadgetbridge", minutes=120))
    before = [dict(r) for r in store.hourly_since(0)]
    removed = store.purge_detail(DAY0 + 86400)
    assert removed > 0
    assert store.totals_between(0, 2**40)["minutes"] == 0
    store.recompute_hours({r["hour_ts"] for r in before})  # must not wipe history
    assert [dict(r) for r in store.hourly_since(0)] == before


def test_running_total_is_rewritten_after_backfill(store, tmp_path):
    _sync(store, make_export(tmp_path / "Gadgetbridge", minutes=120))
    late = sum_rows(store, STATS_BY_KEY["steps"], 0)
    assert late[-1]["sum"] == 108 * 20

    # Older data arrives later (as a Fitbit import would): an hour of 50 steps a minute.
    older = DAY0
    store.ingest(
        "minute",
        [gb.normalise_row(MINUTE, {"TIMESTAMP": older + i * 60, "DEVICE_ID": 2, "STEPS": 50})
         for i in range(60)],
    )
    rows = rows_for_change(store, "minute", older, SYDNEY)["steps"]
    assert rows[0]["sum"] == 3000
    assert rows[-1]["sum"] == 3000 + 108 * 20
    sums = [r["sum"] for r in rows]
    assert sums == sorted(sums)


def test_sleep_credited_to_wake_day(store, tmp_path):
    _sync(store, make_export(tmp_path / "Gadgetbridge", minutes=10))
    sleep = rows_for_change(store, "sleep_session", DAY0 - 86400, SYDNEY)
    (night,) = sleep["sleep_duration"]
    assert night["mean"] == 8.0
    assert night["start"].timestamp() == DAY0  # local midnight of the wake day
    assert sleep["deep_sleep"][0]["mean"] == 1.5


def test_daily_rows_land_on_local_midnight(store, tmp_path):
    _sync(store, make_export(tmp_path / "Gadgetbridge", minutes=10))
    daily = rows_for_change(store, "daily", 0, SYDNEY)
    assert daily["resting_heart_rate"][0]["mean"] == 58
    assert daily["resting_heart_rate"][0]["start"].timestamp() == DAY0


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"protocol": 99, "table": MINUTE.name, "columns": ["TIMESTAMP"], "rows": []},
        {"protocol": 1, "table": "USER", "columns": ["TIMESTAMP"], "rows": []},
        {"protocol": 1, "table": MINUTE.name, "columns": ["STEPS"], "rows": []},
        {"protocol": 1, "table": MINUTE.name, "columns": ["TIMESTAMP"], "rows": [[1, 2]]},
        {"protocol": 1, "table": MINUTE.name, "columns": ["TIMESTAMP"],
         "rows": [[1]] * (MAX_ROWS_PER_BATCH + 1)},
    ],
)
def test_bad_batches_are_rejected(payload):
    with pytest.raises(ProtocolError):
        parse_batch(payload)


def test_unrequested_columns_are_dropped():
    batch = parse_batch(
        {"protocol": 1, "table": MINUTE.name, "columns": ["TIMESTAMP", "DEVICE_ID", "SECRET"],
         "rows": [[100, 1, "x"]]}
    )
    assert "SECRET" not in batch.rows[0]
