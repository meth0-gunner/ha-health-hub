"""Config flow for Health Hub: one entry, two options."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .const import (
    CONF_OVERLAP_HOURS,
    CONF_RETENTION_DAYS,
    DEFAULT_OVERLAP_HOURS,
    DEFAULT_RETENTION_DAYS,
    DOMAIN,
    NAME,
)


class HealthHubConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title=NAME, data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HealthHubOptionsFlow()


class HealthHubOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_RETENTION_DAYS,
                    default=options.get(CONF_RETENTION_DAYS, DEFAULT_RETENTION_DAYS),
                ): vol.All(vol.Coerce(int), vol.Range(min=7, max=3650)),
                vol.Required(
                    CONF_OVERLAP_HOURS,
                    default=options.get(CONF_OVERLAP_HOURS, DEFAULT_OVERLAP_HOURS),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=336)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
