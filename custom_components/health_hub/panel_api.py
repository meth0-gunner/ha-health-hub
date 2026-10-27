"""Websocket commands behind the Health page (admin only).

    health_hub/info           settings, sources, time zone, version
    health_hub/day            everything for one day (Overview and day views)
    health_hub/range          per-day figures between two dates (trend views)
    health_hub/night          one night in full (Sleep page)
    health_hub/sleep_history  sleep by month since records began
    health_hub/settings/set   change goals and settings
    health_hub/training/log   log a gym or Compex session on a day
    health_hub/training/undo  remove a logged session
    health_hub/rewards/spend  take one reward off the balance
    health_hub/weight/log     add a weigh-in
    health_hub/weight/delete  remove a weigh-in
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .core import training, views
from .core.settings import SettingsError
from .core.training import TrainingError

MAX_RANGE_DAYS = 400


def _hub(hass: HomeAssistant):
    from .api import _hub as find  # the same lookup the sync endpoints use

    return find(hass)


def _date(value: Any) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as err:
        raise vol.Invalid("expected a date like 2026-10-27") from err


def _command(schema: dict, handler):
    """Admin-only async websocket command that finds the hub first."""

    @websocket_api.websocket_command(schema)
    @websocket_api.require_admin
    @websocket_api.async_response
    async def run(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
        hub = _hub(hass)
        if hub is None:
            connection.send_error(msg["id"], "not_loaded", "Health Hub is not loaded")
            return
        try:
            result = await handler(hass, hub, msg)
        except (SettingsError, TrainingError, vol.Invalid, ValueError) as err:
            connection.send_error(msg["id"], "invalid", str(err))
            return
        connection.send_result(msg["id"], result)

    return run


def _today() -> date:
    return dt_util.now().date()


async def _info(hass, hub, msg):
    from homeassistant.loader import async_get_integration

    from .const import DOMAIN

    integration = await async_get_integration(hass, DOMAIN)
    settings = await hass.async_add_executor_job(hub.settings)
    first = await hass.async_add_executor_job(hub.store.first_data_ts)
    snap = hub.snapshot
    return {
        "version": str(integration.version),
        "time_zone": str(dt_util.get_default_time_zone()),
        "today": _today().isoformat(),
        "first_date": dt_util.as_local(dt_util.utc_from_timestamp(first)).date().isoformat() if first else None,
        "last_sync": snap.last_sync.isoformat() if snap.last_sync else None,
        "last_reading": snap.last_reading_ts,
        "settings": views.settings_view(settings),
        "sources": views.sources_view(),
    }


async def _day(hass, hub, msg):
    day = _date(msg["date"]) if msg.get("date") else _today()
    settings = await hass.async_add_executor_job(hub.settings)
    return await hass.async_add_executor_job(
        views.day_view, hub.calc, hub.store, settings, day, _today(), int(time.time())
    )


async def _range(hass, hub, msg):
    first, last = _date(msg["start"]), _date(msg["end"])
    if last < first or (last - first).days >= MAX_RANGE_DAYS:
        raise ValueError(f"range must be 1 to {MAX_RANGE_DAYS} days")
    settings = await hass.async_add_executor_job(hub.settings)
    return await hass.async_add_executor_job(views.range_view, hub.calc, settings, first, last)


async def _night(hass, hub, msg):
    settings = await hass.async_add_executor_job(hub.settings)
    return await hass.async_add_executor_job(views.night_view, hub.calc, settings, _date(msg["date"]))


async def _sleep_history(hass, hub, msg):
    settings = await hass.async_add_executor_job(hub.settings)
    return await hass.async_add_executor_job(views.long_term_sleep, hub.calc, settings, _today())


async def _settings_set(hass, hub, msg):
    new = await hub.async_update_settings(msg["changes"])
    return views.settings_view(new)


async def _training_state(hass, hub, day: date):
    settings = await hass.async_add_executor_job(hub.settings)
    return await hass.async_add_executor_job(training.state, hub.store, settings, _today(), day)


async def _training(hass, hub, msg):
    return await _training_state(hass, hub, _date(msg["date"]) if msg.get("date") else _today())


async def _training_log(hass, hub, msg):
    day = _date(msg["date"])
    if day > _today():
        raise ValueError("can't log a session in the future")
    await hub.async_log_training(day, msg["kind"], msg.get("variant"))
    return await _training_state(hass, hub, day)


async def _training_undo(hass, hub, msg):
    await hub.async_undo_training(msg["log_id"])
    return await _training_state(hass, hub, _date(msg["date"]) if msg.get("date") else _today())


async def _spend(hass, hub, msg):
    await hub.async_spend_reward()
    return await _training_state(hass, hub, _date(msg["date"]) if msg.get("date") else _today())


async def _weight_log(hass, hub, msg):
    day = _date(msg["date"]) if msg.get("date") else _today()
    if day > _today():
        raise ValueError("can't log a weight in the future")
    if day == _today():
        ts = int(time.time())
    else:
        noon = datetime.combine(day, datetime.min.time(), dt_util.get_default_time_zone()) + timedelta(hours=8)
        ts = int(noon.timestamp())
    await hub.async_log_weight(round(float(msg["kg"]), 2), ts)
    settings = await hass.async_add_executor_job(hub.settings)
    return await hass.async_add_executor_job(views.weight_view, hub.store, settings, hub.calc.tz)


async def _weight_delete(hass, hub, msg):
    await hub.async_delete_weight(int(msg["ts"]))
    settings = await hass.async_add_executor_job(hub.settings)
    return await hass.async_add_executor_job(views.weight_view, hub.store, settings, hub.calc.tz)


COMMANDS = [
    _command({vol.Required("type"): "health_hub/info"}, _info),
    _command({vol.Required("type"): "health_hub/day", vol.Optional("date"): str}, _day),
    _command({vol.Required("type"): "health_hub/range", vol.Required("start"): str, vol.Required("end"): str}, _range),
    _command({vol.Required("type"): "health_hub/night", vol.Required("date"): str}, _night),
    _command({vol.Required("type"): "health_hub/sleep_history"}, _sleep_history),
    _command({vol.Required("type"): "health_hub/settings/set", vol.Required("changes"): dict}, _settings_set),
    _command({vol.Required("type"): "health_hub/training", vol.Optional("date"): str}, _training),
    _command(
        {
            vol.Required("type"): "health_hub/training/log",
            vol.Required("date"): str,
            vol.Required("kind"): vol.In(["gym", "compex"]),
            vol.Optional("variant"): vol.Any(None, vol.In(["push", "pull", "legs"])),
        },
        _training_log,
    ),
    _command(
        {vol.Required("type"): "health_hub/training/undo", vol.Required("log_id"): int, vol.Optional("date"): str},
        _training_undo,
    ),
    _command({vol.Required("type"): "health_hub/rewards/spend", vol.Optional("date"): str}, _spend),
    _command(
        {
            vol.Required("type"): "health_hub/weight/log",
            vol.Required("kg"): vol.All(vol.Coerce(float), vol.Range(min=20, max=400)),
            vol.Optional("date"): str,
        },
        _weight_log,
    ),
    _command({vol.Required("type"): "health_hub/weight/delete", vol.Required("ts"): int}, _weight_delete),
]


@callback
def async_register(hass: HomeAssistant) -> None:
    for command in COMMANDS:
        websocket_api.async_register_command(hass, command)
