"""Importing history (Fitbit) into the store and statistics."""

from __future__ import annotations

import gzip
import json
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.health_hub.const import DOMAIN
from custom_components.health_hub.core import gadgetbridge as gb
from custom_components.health_hub.core.history import HistoryError, load_history_file, parse_history
from custom_components.health_hub.core.stats import rows_for_full_rebuild
from custom_components.health_hub.core.store import Store

from .test_fitbit_takeout import make_takeout

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import fitbit_takeout  # noqa: E402

SYDNEY = ZoneInfo("Australia/Sydney")
MINUTE = gb.TABLES_BY_NAME["XIAOMI_ACTIVITY_SAMPLE"]
UPLOAD_ID = "6f1c2a1e-3b4d-4c5e-8f60-718293a4b5c6"


def _epoch(s: str) -> int:
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


@pytest.fixture
def history_file(tmp_path) -> Path:
    data = fitbit_takeout.convert([str(make_takeout(tmp_path / "takeout.zip"))])
    path = tmp_path / "fitbit-history.json.gz"
    with gzip.open(path, "wt") as f:
        json.dump(data, f)
    return path


def test_load_and_import(tmp_path, history_file):
    store = Store(tmp_path / "hub.db")
    history = load_history_file(history_file)
    counts = store.import_history(history)
    assert counts == {"hours": 2, "days": 1, "sleeps": 2, "measurements": 1}

    stats = rows_for_full_rebuild(store, SYDNEY)
    assert stats["steps"][-1]["sum"] == 105
    assert stats["heart_rate"][0]["mean"] == 80.0
    assert stats["hrv"][0]["mean"] == 21.5
    assert stats["weight"][0]["mean"] == 90.3
    # Weighed at 21:00 UTC on 1 June = 7am on 2 June in Sydney.
    assert stats["weight"][0]["start"] == datetime(2025, 6, 1, 14, tzinfo=timezone.utc)
    assert stats["resting_heart_rate"][0]["start"] == datetime(2025, 5, 31, 14, tzinfo=timezone.utc)
    night = stats["sleep_duration"][0]
    assert night["mean"] == round(440 / 60, 2)
    assert stats["sleep_score"][0]["mean"] == 81.2

    # Importing again replaces rather than adds.
    store.import_history(history)
    assert rows_for_full_rebuild(store, SYDNEY)["steps"][-1]["sum"] == 105
    store.close()


def test_band_wins_over_import(tmp_path, history_file):
    store = Store(tmp_path / "hub.db")
    hour = _epoch("2025-06-01T00:00:00Z")
    store.ingest(
        "minute",
        [gb.normalise_row(MINUTE, {"TIMESTAMP": hour + i * 60, "DEVICE_ID": 1, "STEPS": 1})
         for i in range(10)],
    )
    store.import_history(load_history_file(history_file))
    rows = {r["hour_ts"]: r for r in store.hourly_since(0)}
    assert rows[hour]["steps"] == 10 and rows[hour]["source"] == "band"
    assert rows[hour + 3600]["source"] == "fitbit"

    # A band sleep on the same day replaces the imported one.
    store.ingest(
        "sleep_session",
        [{"device_id": 1, "ts": _epoch("2025-06-01T12:30:00Z"), "wakeup_ts": _epoch("2025-06-01T19:30:00Z"),
          "is_awake": 0, "total_min": 400, "deep_min": 60, "light_min": 240, "rem_min": 100,
          "awake_min": 20}],
    )
    sleep = rows_for_full_rebuild(store, SYDNEY)["sleep_duration"]
    assert [r["mean"] for r in sleep] == [round(400 / 60, 2), round(80 / 60, 2)]
    store.close()


def test_upgrade_from_first_version(tmp_path):
    path = tmp_path / "hub.db"
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE sleep_sessions (device_id INTEGER NOT NULL, ts INTEGER NOT NULL,"
        " wakeup_ts INTEGER, is_awake INTEGER, total_min INTEGER, deep_min INTEGER,"
        " light_min INTEGER, rem_min INTEGER, awake_min INTEGER, PRIMARY KEY (device_id, ts))"
        " WITHOUT ROWID"
    )
    db.execute("INSERT INTO sleep_sessions VALUES (1, 100, 200, 0, 60, 10, 30, 15, 5)")
    db.commit()
    db.close()
    store = Store(path)
    assert store.latest_row("sleep_sessions")["score"] is None
    store.close()


@pytest.mark.parametrize(
    "data",
    [
        {"format": "something_else", "version": 1},
        {"format": "health_hub_history", "version": 2},
        {"format": "health_hub_history", "version": 1, "source": "band"},
        {"format": "health_hub_history", "version": 1,
         "hourly": {"columns": ["hour_ts"], "rows": [[1]]}},
        {"format": "health_hub_history", "version": 1,
         "daily": {"columns": ["metric", "date", "value"], "rows": [["hrv", "June", 3]]}},
    ],
)
def test_bad_history_rejected(data):
    with pytest.raises(HistoryError):
        parse_history(data)


async def test_upload_in_home_assistant(
    recorder_mock, enable_custom_integrations, hass: HomeAssistant, tmp_path, history_file
):
    hass.config.config_dir = str(tmp_path)
    await hass.config.async_set_time_zone("Australia/Sydney")
    entry = MockConfigEntry(domain=DOMAIN, title="Health Hub", data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    @contextmanager
    def fake_upload(_hass, file_id):
        assert file_id == UPLOAD_ID
        yield history_file

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "import_history"}
    )
    assert flow["type"] is FlowResultType.FORM
    with patch("custom_components.health_hub.config_flow.process_uploaded_file", fake_upload):
        result = await hass.config_entries.options.async_configure(
            flow["flow_id"], {"history_file": UPLOAD_ID}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "history_imported"
    assert result["description_placeholders"]["sleeps"] == "2"

    await async_wait_recording_done(hass)
    stats = await hass.async_add_executor_job(
        statistics_during_period,
        hass,
        dt_util.utc_from_timestamp(_epoch("2025-05-01T00:00:00Z")),
        None,
        {f"{DOMAIN}:steps", f"{DOMAIN}:hrv", f"{DOMAIN}:sleep_score"},
        "hour",
        None,
        {"sum", "mean"},
    )
    assert stats[f"{DOMAIN}:steps"][-1]["sum"] == 105
    assert stats[f"{DOMAIN}:hrv"][0]["mean"] == 21.5
    assert stats[f"{DOMAIN}:sleep_score"][0]["mean"] == 81.2


async def test_upload_rejects_wrong_file(
    recorder_mock, enable_custom_integrations, hass: HomeAssistant, tmp_path
):
    hass.config.config_dir = str(tmp_path)
    entry = MockConfigEntry(domain=DOMAIN, title="Health Hub", data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    wrong = tmp_path / "photo.json"
    wrong.write_text('{"hello": 1}')

    @contextmanager
    def fake_upload(_hass, _file_id):
        yield wrong

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "import_history"}
    )
    with patch("custom_components.health_hub.config_flow.process_uploaded_file", fake_upload):
        result = await hass.config_entries.options.async_configure(
            flow["flow_id"], {"history_file": UPLOAD_ID}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_file"}
