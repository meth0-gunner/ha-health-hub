"""Health Hub: a cloud-free Fitbit-app replacement for Gadgetbridge bands."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from datetime import timedelta

from homeassistant.helpers.event import async_track_time_change, async_track_time_interval
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from . import panel_api
from .api import async_register_api
from .const import DOMAIN
from .hub import HealthHub
from .review import ReviewManager

PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type HealthHubConfigEntry = ConfigEntry[HealthHub]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    # Views and commands can only be registered once per HA run, so they look
    # up the loaded entry on each request rather than holding a reference.
    async_register_api(hass)
    panel_api.async_register(hass)
    await _async_register_static(hass)

    async def rebuild(call: ServiceCall) -> None:
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            await entry.runtime_data.async_rebuild_statistics()

    async def request_review(call: ServiceCall) -> None:
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            await entry.runtime_data.reviews.async_request("manual")

    def _hubs():
        return [e.runtime_data for e in hass.config_entries.async_loaded_entries(DOMAIN)]

    async def log_weight(call: ServiceCall) -> None:
        for hub in _hubs():
            await hub.async_log_weight(round(call.data["weight"], 2), int(dt_util.utcnow().timestamp()))

    async def log_training(call: ServiceCall) -> None:
        for hub in _hubs():
            await hub.async_log_training(dt_util.now().date(), call.data["kind"], call.data.get("variant"))

    async def spend_reward(call: ServiceCall) -> None:
        for hub in _hubs():
            await hub.async_spend_reward()

    hass.services.async_register(DOMAIN, "rebuild_statistics", rebuild)
    hass.services.async_register(DOMAIN, "request_review", request_review)
    hass.services.async_register(
        DOMAIN, "log_weight", log_weight,
        schema=vol.Schema({vol.Required("weight"): vol.All(vol.Coerce(float), vol.Range(min=20, max=400))}),
    )
    hass.services.async_register(
        DOMAIN, "log_training", log_training,
        schema=vol.Schema({
            vol.Required("kind"): vol.In(["gym", "compex"]),
            vol.Optional("variant"): vol.In(["push", "pull", "legs"]),
        }),
    )
    hass.services.async_register(DOMAIN, "spend_reward", spend_reward)
    return True


STATIC_URL = "/health_hub_static"
PANEL_URL = "health"


async def _async_register_static(hass: HomeAssistant) -> None:
    from homeassistant.components.http import StaticPathConfig
    from homeassistant.loader import async_get_integration

    version = (await async_get_integration(hass, DOMAIN)).version
    hass.data[f"{DOMAIN}_static"] = f"{STATIC_URL}/{version}"
    # The version is in the path, so the browser fetches new files after an update.
    await hass.http.async_register_static_paths(
        [StaticPathConfig(f"{STATIC_URL}/{version}", str(Path(__file__).parent / "frontend"), True)]
    )


async def _async_register_panel(hass: HomeAssistant) -> None:
    from homeassistant.components import panel_custom

    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name="health-hub-panel",
        sidebar_title="Health",
        sidebar_icon="mdi:heart-pulse",
        module_url=f"{hass.data[f'{DOMAIN}_static']}/panel.js",
        require_admin=True,
        config={},
    )


async def async_setup_entry(hass: HomeAssistant, entry: HealthHubConfigEntry) -> bool:
    hub = await HealthHub.async_create(hass, entry)
    entry.runtime_data = hub
    hub.reviews = ReviewManager(hass, hub)
    hub.on_sleep_synced = hub.reviews.async_sleep_synced
    await hub.reviews.async_start()
    entry.async_on_unload(hub.reviews.async_stop)

    async def _midnight(_now: datetime) -> None:
        await hub.async_refresh()  # "today" totals start again

    async def _nightly(_now: datetime) -> None:
        await hub.async_purge()

    entry.async_on_unload(async_track_time_change(hass, _midnight, hour=0, minute=0, second=5))
    entry.async_on_unload(async_track_time_change(hass, _nightly, hour=3, minute=37, second=0))
    entry.async_on_unload(async_track_time_interval(hass, _midnight, timedelta(minutes=15)))  # energy moves
    entry.async_on_unload(entry.add_update_listener(_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _async_register_panel(hass)
    return True


async def _options_updated(hass: HomeAssistant, entry: HealthHubConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HealthHubConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        from homeassistant.components import frontend

        frontend.async_remove_panel(hass, PANEL_URL)
        await entry.runtime_data.async_close()
    return unloaded
