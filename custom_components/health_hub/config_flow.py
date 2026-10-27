"""Config flow for Health Hub: one entry; options for settings and history import."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import FileSelector, FileSelectorConfig

from .const import (
    CONF_OVERLAP_HOURS,
    CONF_RETENTION_DAYS,
    DEFAULT_OVERLAP_HOURS,
    DEFAULT_RETENTION_DAYS,
    DOMAIN,
    NAME,
)
from .core.history import History, HistoryError, load_history_file

_LOGGER = logging.getLogger(__name__)
CONF_HISTORY_FILE = "history_file"


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


def _read_upload(hass: HomeAssistant, file_id: str) -> History:
    with process_uploaded_file(hass, file_id) as path:
        return load_history_file(path)


class HealthHubOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["settings", "import_history"])

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
        return self.async_show_form(step_id="settings", data_schema=schema)

    async def async_step_import_history(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        if user_input is not None:
            try:
                history = await self.hass.async_add_executor_job(
                    _read_upload, self.hass, user_input[CONF_HISTORY_FILE]
                )
            except HistoryError as err:
                errors["base"] = "invalid_file"
                placeholders["error"] = str(err)
            except Exception:  # noqa: BLE001 - shown to the user, details in the log
                _LOGGER.exception("Could not read the uploaded history file")
                errors["base"] = "unknown"
            else:
                counts = await self.config_entry.runtime_data.async_import_history(history)
                return self.async_abort(
                    reason="history_imported",
                    description_placeholders={k: f"{v:,}" for k, v in counts.items()},
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_HISTORY_FILE): FileSelector(
                    FileSelectorConfig(accept=".gz,.json,application/gzip,application/json")
                )
            }
        )
        return self.async_show_form(
            step_id="import_history",
            data_schema=schema,
            errors=errors,
            description_placeholders=placeholders,
        )
