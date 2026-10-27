"""Endpoints the phone app calls, and the dashboard's data command.

    GET  /api/health_hub/sync/plan   what to send, and from when
    POST /api/health_hub/sync/batch  one batch of rows

Both need an admin user's access token. Websocket commands (admin only):
`health_hub/samples` returns minute-level readings for charts, and
`health_hub/review` the daily review (latest, a given one, or the history).
"""

from __future__ import annotations

import json
import logging
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from aiohttp import web
from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .core.protocol import ProtocolError
from .core.store import SAMPLE_METRICS

if TYPE_CHECKING:
    from .hub import HealthHub

_LOGGER = logging.getLogger(__name__)
MAX_BODY_BYTES = 8 * 1024 * 1024


def _hub(hass: HomeAssistant) -> HealthHub | None:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            return entry.runtime_data
    return None


class _BaseView(HomeAssistantView):
    requires_auth = True

    def _check(self, request: web.Request) -> tuple[HomeAssistant, HealthHub | None, web.Response | None]:
        hass: HomeAssistant = request.app["hass"]
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            return hass, None, self.json_message("Admin access required", HTTPStatus.FORBIDDEN)
        hub = _hub(hass)
        if hub is None:
            return hass, None, self.json_message(
                "Health Hub is not loaded", HTTPStatus.SERVICE_UNAVAILABLE
            )
        return hass, hub, None


class SyncPlanView(_BaseView):
    url = "/api/health_hub/sync/plan"
    name = "api:health_hub:sync_plan"

    async def get(self, request: web.Request) -> web.Response:
        _hass, hub, error = self._check(request)
        if error:
            return error
        return self.json(await hub.async_plan())


class SyncBatchView(_BaseView):
    url = "/api/health_hub/sync/batch"
    name = "api:health_hub:sync_batch"

    async def post(self, request: web.Request) -> web.Response:
        _hass, hub, error = self._check(request)
        if error:
            return error
        if request.content_length and request.content_length > MAX_BODY_BYTES:
            return self.json_message("Batch too large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        try:
            payload = await request.json()
        except ValueError:
            return self.json_message("Body is not valid JSON", HTTPStatus.BAD_REQUEST)
        try:
            result = await hub.async_ingest(payload)
        except ProtocolError as err:
            _LOGGER.warning("Rejected batch from phone: %s", err)
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        return self.json(result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "health_hub/samples",
        vol.Required("metric"): vol.In(sorted(SAMPLE_METRICS)),
        vol.Required("start"): vol.Coerce(float),
        vol.Required("end"): vol.Coerce(float),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_samples(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Readings between two times (epoch seconds), as [[epoch_ms, value], ...]."""
    hub = _hub(hass)
    if hub is None:
        connection.send_error(msg["id"], "not_loaded", "Health Hub is not loaded")
        return
    start, end = int(msg["start"]), int(msg["end"])
    if end <= start or end - start > 31 * 86400:
        connection.send_error(msg["id"], "invalid_range", "Range must be 1 to 31 days")
        return
    points = await hass.async_add_executor_job(hub.store.samples, msg["metric"], start, end)
    connection.send_result(msg["id"], {"points": [[ts * 1000, v] for ts, v in points]})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "health_hub/review",
        vol.Optional("review_id"): str,
        vol.Optional("history", default=False): bool,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_review(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """The latest review and the reviewer's state; or one review; or the list."""
    hub = _hub(hass)
    if hub is None:
        connection.send_error(msg["id"], "not_loaded", "Health Hub is not loaded")
        return
    reviews = hub.reviews
    result = reviews.overview()
    if "review_id" in msg:
        row = await hass.async_add_executor_job(hub.store.get_review, msg["review_id"])
        if row is None:
            connection.send_error(msg["id"], "not_found", "No such review")
            return
        result["review"] = reviews.as_dict(row)
    if msg["history"]:
        rows = await hass.async_add_executor_job(hub.store.review_history)
        result["history"] = [
            {
                "id": r["id"],
                "day": r["day"],
                "status": r["status"],
                "reason": r["reason"],
                "error": r["error"],
                "headline": json.loads(r["review_json"]).get("headline") if r["review_json"] else None,
            }
            for r in rows
        ]
    connection.send_result(msg["id"], result)


@callback
def async_register_api(hass: HomeAssistant) -> None:
    hass.http.register_view(SyncPlanView())
    hass.http.register_view(SyncBatchView())
    websocket_api.async_register_command(hass, ws_samples)
    websocket_api.async_register_command(hass, ws_review)
