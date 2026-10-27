"""End to end: a test Home Assistant receives a synthetic Gadgetbridge export."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.health_hub.const import DOMAIN

from .gbfixture import make_export

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import sync_export  # noqa: E402

PLAN = "/api/health_hub/sync/plan"
BATCH = "/api/health_hub/sync/batch"


@pytest.fixture
async def hub_entry(recorder_mock, enable_custom_integrations, hass: HomeAssistant, tmp_path):
    # Order matters: the recorder must start before Home Assistant does.
    hass.config.config_dir = str(tmp_path)
    await hass.config.async_set_time_zone("Australia/Sydney")
    entry = MockConfigEntry(domain=DOMAIN, title="Health Hub", data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _sync_via_http(client, export: Path) -> dict[str, int]:
    """Drive the real HTTP endpoints with the reference client's reading logic."""
    plan = await (await client.get(PLAN)).json()
    db = sqlite3.connect(f"file:{export}?mode=ro", uri=True)
    devices = sync_export.read_devices(db, plan)
    sent: dict[str, int] = {}
    for table in plan["tables"]:
        for cols, rows in sync_export.read_batches(db, table, plan["max_rows"]):
            resp = await client.post(
                BATCH,
                json={"protocol": 1, "table": table["name"], "columns": cols,
                      "rows": rows, "devices": devices},
            )
            assert resp.status == 200, await resp.text()
            sent[table["name"]] = sent.get(table["name"], 0) + len(rows)
    db.close()
    return sent


async def test_sync_end_to_end(hub_entry, hass: HomeAssistant, hass_client, tmp_path):
    now = dt_util.now()
    start = int(dt_util.start_of_local_day(now).timestamp()) + 60  # today, so sensors count it
    export = make_export(tmp_path / "Gadgetbridge", minutes=90, start=start)

    client = await hass_client()
    sent = await _sync_via_http(client, export)
    assert sent["XIAOMI_ACTIVITY_SAMPLE"] == 90
    await hass.async_block_till_done()

    steps = hass.states.get("sensor.health_hub_steps_today")
    assert steps is not None and int(steps.state) == 81 * 20
    assert hass.states.get("sensor.health_hub_heart_rate").state in {"70", "71", "72", "73", "74"}
    assert hass.states.get("sensor.health_hub_band_battery").state == "87"
    assert float(hass.states.get("sensor.health_hub_last_sleep").state) == 8.0
    assert hass.states.get("sensor.health_hub_resting_heart_rate").state == "58"
    assert hass.states.get("sensor.health_hub_last_sync").state not in ("unknown", "unavailable")

    await async_wait_recording_done(hass)
    stats = await hass.async_add_executor_job(
        statistics_during_period,
        hass,
        dt_util.utc_from_timestamp(start - 3600),
        None,
        {f"{DOMAIN}:steps", f"{DOMAIN}:heart_rate"},
        "hour",
        None,
        {"sum", "mean", "max"},
    )
    assert stats[f"{DOMAIN}:steps"][-1]["sum"] == 81 * 20
    assert 70 <= stats[f"{DOMAIN}:heart_rate"][0]["mean"] <= 74

    # A second sync re-sends the overlap without double counting.
    await _sync_via_http(client, export)
    await hass.async_block_till_done()
    assert int(hass.states.get("sensor.health_hub_steps_today").state) == 81 * 20


async def test_samples_websocket(hub_entry, hass: HomeAssistant, hass_client, hass_ws_client, tmp_path):
    start = int(dt_util.start_of_local_day().timestamp()) + 60
    await _sync_via_http(await hass_client(), make_export(tmp_path / "GB", minutes=30, start=start))
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "health_hub/samples", "metric": "heart_rate",
                        "start": start, "end": start + 3600})
    msg = await ws.receive_json()
    assert msg["success"]
    assert len(msg["result"]["points"]) == 27
    assert msg["result"]["points"][0][0] == (start + 60) * 1000


async def test_non_admin_is_refused(hub_entry, hass: HomeAssistant, hass_client, hass_read_only_user):
    refresh = await hass.auth.async_create_refresh_token(
        hass_read_only_user, client_id="https://example.com"
    )
    token = hass.auth.async_create_access_token(refresh)
    client = await hass_client(access_token=token)
    resp = await client.get(PLAN)
    assert resp.status == 403


async def test_bad_batch_is_rejected(hub_entry, hass: HomeAssistant, hass_client):
    client = await hass_client()
    resp = await client.post(BATCH, json={"protocol": 1, "table": "USER", "columns": [], "rows": []})
    assert resp.status == 400


async def test_unload(hub_entry, hass: HomeAssistant):
    assert await hass.config_entries.async_unload(hub_entry.entry_id)
    await hass.async_block_till_done()
