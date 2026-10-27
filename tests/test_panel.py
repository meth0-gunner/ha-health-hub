"""The Health panel: registered, its files served, and its commands working."""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest
from homeassistant.components.frontend import DATA_PANELS
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.health_hub.const import DOMAIN

from .gbfixture import make_export
from .test_integration import _sync_via_http

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))


@pytest.fixture
async def hub_entry(recorder_mock, enable_custom_integrations, hass: HomeAssistant, tmp_path):
    hass.config.config_dir = str(tmp_path)
    await hass.config.async_set_time_zone("Australia/Sydney")
    entry = MockConfigEntry(domain=DOMAIN, title="Health Hub", data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _ws(client, n: int, **msg):
    await client.send_json({"id": n, **msg})
    reply = await client.receive_json()
    return reply


async def test_panel_registered_and_served(hub_entry, hass: HomeAssistant, hass_client):
    panel = hass.data[DATA_PANELS]["health"]
    assert panel.require_admin
    assert panel.sidebar_title == "Health"
    url = panel.config["_panel_custom"]["module_url"]
    client = await hass_client()
    resp = await client.get(url)
    assert resp.status == 200
    assert "health-hub-panel" in await resp.text()
    # Every module the panel imports is served too.
    for name in ("style.js", "charts.js", "util.js", "parts.js", "pages/overview.js", "pages/sleep.js"):
        assert (await client.get(url.rsplit("/", 1)[0] + "/" + name)).status == 200


async def test_commands(hub_entry, hass: HomeAssistant, hass_client, hass_ws_client, tmp_path):
    await _sync_via_http(await hass_client(), make_export(tmp_path / "gb.db", minutes=600))
    ws = await hass_ws_client(hass)
    today = dt_util.now().date().isoformat()
    week_ago = (dt_util.now().date() - timedelta(days=6)).isoformat()

    info = await _ws(ws, 1, type="health_hub/info")
    assert info["success"], info
    assert info["result"]["settings"]["steps_goal"] == 10000

    for n, msg in enumerate(
        [
            {"type": "health_hub/day"},
            {"type": "health_hub/range", "start": week_ago, "end": today},
            {"type": "health_hub/night", "date": today},
            {"type": "health_hub/sleep_history"},
            {"type": "health_hub/training"},
        ],
        start=2,
    ):
        reply = await _ws(ws, n, **msg)
        assert reply["success"], (msg, reply)

    logged = await _ws(ws, 10, type="health_hub/training/log", date=today, kind="gym", variant="push")
    assert logged["success"], logged
    state = logged["result"]
    assert state["gym"]["count"] == 1
    log_id = state["day_logs"][0]["id"] if "day_logs" in state else state["today"][0]["id"]
    undone = await _ws(ws, 11, type="health_hub/training/undo", log_id=log_id, date=today)
    assert undone["success"] and undone["result"]["gym"]["count"] == 0

    future = (dt_util.now().date() + timedelta(days=1)).isoformat()
    refused = await _ws(ws, 12, type="health_hub/training/log", date=future, kind="compex")
    assert not refused["success"]

    spend = await _ws(ws, 13, type="health_hub/rewards/spend")
    assert not spend["success"]  # nothing earned yet

    weight = await _ws(ws, 14, type="health_hub/weight/log", kg=88.4)
    assert weight["success"], weight
    changed = await _ws(ws, 15, type="health_hub/settings/set", changes={"steps_goal": 8000, "weight_goal_kg": 85})
    assert changed["success"], changed
    assert changed["result"]["steps_goal"] == 8000

    bad = await _ws(ws, 16, type="health_hub/settings/set", changes={"steps_goal": -5})
    assert not bad["success"]


async def test_non_admin_refused(hub_entry, hass: HomeAssistant, hass_ws_client, hass_read_only_access_token):
    ws = await hass_ws_client(hass, hass_read_only_access_token)
    reply = await _ws(ws, 1, type="health_hub/info")
    assert not reply["success"]
