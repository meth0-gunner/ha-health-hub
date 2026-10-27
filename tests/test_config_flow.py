"""The add-integration and options screens."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.health_hub.const import CONF_RETENTION_DAYS, DOMAIN


async def test_add_then_options(recorder_mock, enable_custom_integrations, hass: HomeAssistant, tmp_path):
    hass.config.config_dir = str(tmp_path)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    # Only one Health Hub is allowed.
    again = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert again["type"] is FlowResultType.ABORT

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    options = await hass.config_entries.options.async_init(entry.entry_id)
    assert options["type"] is FlowResultType.MENU
    options = await hass.config_entries.options.async_configure(
        options["flow_id"], {"next_step_id": "settings"}
    )
    options = await hass.config_entries.options.async_configure(
        options["flow_id"], {CONF_RETENTION_DAYS: 120, "overlap_hours": 24}
    )
    assert options["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_RETENTION_DAYS] == 120
