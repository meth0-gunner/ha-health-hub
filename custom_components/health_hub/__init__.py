"""Health Hub: a cloud-free Fitbit-app replacement for Gadgetbridge bands."""

from __future__ import annotations

from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType

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

    async def rebuild(call: ServiceCall) -> None:
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            await entry.runtime_data.async_rebuild_statistics()

    async def request_review(call: ServiceCall) -> None:
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            await entry.runtime_data.reviews.async_request("manual")

    hass.services.async_register(DOMAIN, "rebuild_statistics", rebuild)
    hass.services.async_register(DOMAIN, "request_review", request_review)
    return True


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
    entry.async_on_unload(entry.add_update_listener(_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _options_updated(hass: HomeAssistant, entry: HealthHubConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HealthHubConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_close()
    return unloaded
