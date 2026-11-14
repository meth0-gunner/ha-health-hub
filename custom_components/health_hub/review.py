"""The daily review, Home Assistant side.

Each morning, once last night's sleep has synced, Health Hub writes a request
(the prompt with a summary of the figures) to `health_hub/review/request.json`
in the config folder. The Health Hub Reviewer add-on runs it with Claude and
writes `response.json`, which is read back here, checked and kept.

If no sleep has synced by the fallback time, the review is requested anyway.
`health_hub.request_review` asks for one straight away.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_call_later,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_REVIEW_ENABLED,
    CONF_REVIEW_TIME,
    DEFAULT_REVIEW_ENABLED,
    DEFAULT_REVIEW_TIME,
    REVIEW_DIR,
    SIGNAL_REVIEW,
)
from .core.review import (
    LONGEVITY_EVERY_DAYS,
    LONGEVITY_PREFIX,
    ReviewError,
    build_longevity_prompt,
    build_prompt,
    build_summary,
    main_sleep,
    parse_review,
    longevity_summary,
    recent_context,
    sleeps_by_day,
)

if TYPE_CHECKING:
    from .hub import HealthHub

_LOGGER = logging.getLogger(__name__)

POLL_INTERVAL = timedelta(seconds=30)
SETTLE_SECONDS = 10 * 60  # let the rest of the hour's sync land after the sleep
OFFLINE_AFTER = 180  # seconds without a heartbeat from the add-on
GIVE_UP_AFTER = 45 * 60  # a request with no answer by then has failed


def _read_json(path: Path) -> tuple[float, Any] | None:
    try:
        mtime = path.stat().st_mtime
        return mtime, json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class ReviewManager:
    def __init__(self, hass: HomeAssistant, hub: HealthHub) -> None:
        self.hass = hass
        self.hub = hub
        self.dir = Path(hass.config.path(REVIEW_DIR))
        self.latest: dict[str, Any] | None = None  # newest successful review row
        self.last_attempt: dict[str, Any] | None = None  # newest request row, any outcome
        self.lon_latest: dict[str, Any] | None = None  # the monthly Longevity review, likewise
        self.lon_attempt: dict[str, Any] | None = None
        self.reviewer: dict[str, Any] = {}
        self.reviewer_state = "unknown"
        self._response_mtime: float | None = None
        self._settle: CALLBACK_TYPE | None = None
        self._unsubs: list[Callable[[], None]] = []

    # ---------------------------------------------------------------- options

    @property
    def enabled(self) -> bool:
        return self.hub.entry.options.get(CONF_REVIEW_ENABLED, DEFAULT_REVIEW_ENABLED)

    @property
    def fallback_time(self) -> tuple[int, int]:
        value = self.hub.entry.options.get(CONF_REVIEW_TIME, DEFAULT_REVIEW_TIME)
        parsed = dt_util.parse_time(value) or dt_util.parse_time(DEFAULT_REVIEW_TIME)
        return parsed.hour, parsed.minute

    # -------------------------------------------------------------- lifecycle

    async def async_start(self) -> None:
        await self._async_load()
        self._unsubs.append(async_track_time_interval(self.hass, self._async_poll, POLL_INTERVAL))
        hour, minute = self.fallback_time
        self._unsubs.append(
            async_track_time_change(self.hass, self._async_fallback, hour=hour, minute=minute, second=0)
        )
        await self._async_poll()

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._settle:
            self._settle()
            self._settle = None

    async def _async_load(self) -> None:
        store = self.hub.store
        self.latest = await self.hass.async_add_executor_job(store.latest_review, "ok")
        self.last_attempt = await self.hass.async_add_executor_job(store.latest_review)
        self.lon_latest = await self.hass.async_add_executor_job(store.latest_review, "ok", None, "longevity")
        self.lon_attempt = await self.hass.async_add_executor_job(store.latest_review, None, None, "longevity")

    # --------------------------------------------------------------- triggers

    def _today(self) -> str:
        return dt_util.now().date().isoformat()

    def _requested_today(self) -> bool:
        return bool(self.last_attempt and self.last_attempt["day"] == self._today())

    def _ok_today(self) -> bool:
        return bool(self.latest and self.latest["day"] == self._today())

    @callback
    def async_sleep_synced(self) -> None:
        """Called after sleep sessions arrive; start the morning review once per day."""
        if not self.enabled or self._requested_today() or self._settle:
            return
        self.hass.async_create_task(self._async_check_morning())

    async def _async_check_morning(self) -> None:
        tz = dt_util.get_default_time_zone()
        today = dt_util.now().date()
        start = int(dt_util.start_of_local_day().timestamp())
        by_day = await self.hass.async_add_executor_job(sleeps_by_day, self.hub.store, tz, start)
        if not main_sleep(by_day.get(today, [])):
            return  # only a nap so far, or yesterday's night re-sent
        if self._settle or self._requested_today():
            return

        @callback
        def _go(_now: datetime) -> None:
            self._settle = None
            if not self._requested_today():
                self.hass.async_create_task(self.async_request("morning"))

        self._settle = async_call_later(self.hass, SETTLE_SECONDS, _go)

    async def _async_fallback(self, _now: datetime) -> None:
        pending = self.last_attempt and self.last_attempt["status"] == "pending"
        if self.enabled and not self._ok_today() and not pending:
            await self.async_request("scheduled")

    # ---------------------------------------------------------------- request

    def _context(self) -> dict[str, Any] | None:
        """Day-by-day figures, goals and training for trends (best effort)."""
        try:
            from .core import settings as settings_mod

            settings = settings_mod.load(self.hub.store)
            return recent_context(self.hub.calc, self.hub.store, settings, dt_util.now().date())
        except Exception:  # noqa: BLE001 - the review still works without it
            _LOGGER.exception("Could not add the day-by-day figures to the review")
            return None

    @staticmethod
    def _pending(row: dict[str, Any] | None) -> bool:
        return bool(row and row["status"] == "pending" and time.time() - row["requested"] < GIVE_UP_AFTER)

    async def async_request(self, reason: str = "manual") -> str:
        """Write a review request for the add-on and remember it."""
        if self._pending(self.lon_attempt):
            # The add-on takes one request at a time; don't overwrite the monthly one.
            if reason == "manual":
                raise ReviewError("Claude is still writing the monthly Longevity review; try again in a few minutes")
            return ""
        tz = dt_util.get_default_time_zone()
        now = int(time.time())
        extra = await self.hass.async_add_executor_job(self._context)
        summary = await self.hass.async_add_executor_job(
            build_summary, self.hub.store, tz, now, extra
        )
        review_id = f"{summary['date']}-{now}"
        request = {
            "id": review_id,
            "created": dt_util.utcnow().isoformat(timespec="seconds"),
            "day": summary["date"],
            "reason": reason,
            "prompt": build_prompt(summary),
        }
        store = self.hub.store
        await self.hass.async_add_executor_job(
            store.add_review_request, review_id, summary["date"], now, reason, json.dumps(summary)
        )
        await self.hass.async_add_executor_job(_write_json, self.dir / "request.json", request)
        self.last_attempt = await self.hass.async_add_executor_job(store.get_review, review_id)
        _LOGGER.info("Requested the daily review (%s)", reason)
        self._changed()
        return review_id

    def _longevity_summary(self) -> dict[str, Any]:
        from .core import settings as settings_mod
        from .core.longevity import longevity_view

        settings = settings_mod.load(self.hub.store)
        today = dt_util.now().date()
        report = longevity_view(self.hub.calc, self.hub.store, settings, today)
        return longevity_summary(report, settings, today)

    def longevity_due(self) -> bool:
        if not self.enabled or self._pending(self.lon_attempt) or self._pending(self.last_attempt):
            return False
        if self.lon_attempt and self.lon_attempt["status"] != "ok" and time.time() - self.lon_attempt["requested"] < 86400:
            return False  # one try a day after a failure
        last = self.lon_latest["requested"] if self.lon_latest else 0
        return time.time() - last >= LONGEVITY_EVERY_DAYS * 86400

    async def async_request_longevity(self, reason: str = "manual") -> str:
        """Ask for the monthly Longevity review (same add-on, same files)."""
        if self._pending(self.last_attempt) or self._pending(self.lon_attempt):
            raise ReviewError("Claude is still writing another review; try again in a few minutes")
        now = int(time.time())
        summary = await self.hass.async_add_executor_job(self._longevity_summary)
        review_id = f"{LONGEVITY_PREFIX}{summary['date']}-{now}"
        request = {
            "id": review_id,
            "created": dt_util.utcnow().isoformat(timespec="seconds"),
            "day": summary["date"],
            "reason": f"longevity {reason}",
            "prompt": build_longevity_prompt(summary),
        }
        store = self.hub.store
        await self.hass.async_add_executor_job(
            store.add_review_request, review_id, summary["date"], now, f"longevity {reason}", json.dumps(summary)
        )
        await self.hass.async_add_executor_job(_write_json, self.dir / "request.json", request)
        self.lon_attempt = await self.hass.async_add_executor_job(store.get_review, review_id)
        _LOGGER.info("Requested the monthly Longevity review (%s)", reason)
        self._changed()
        return review_id

    # ------------------------------------------------------------------- poll

    async def _async_poll(self, _now: datetime | None = None) -> None:
        status, response = await self.hass.async_add_executor_job(self._read_files)
        changed = self._update_reviewer(status)
        if response is not None:
            changed |= await self._async_take_response(response)
        changed |= await self._async_check_overdue()
        if changed:
            self._changed()

    def _read_files(self) -> tuple[Any, Any]:
        status = _read_json(self.dir / "status.json")
        response = None
        try:
            mtime = (self.dir / "response.json").stat().st_mtime
        except OSError:
            mtime = None
        if mtime is not None and mtime != self._response_mtime:
            found = _read_json(self.dir / "response.json")
            if found:
                self._response_mtime = found[0]
                response = found[1]
        return (status[1] if status else None, status[0] if status else None), response

    def _update_reviewer(self, status: tuple[Any, float | None]) -> bool:
        data, mtime = status
        before = (self.reviewer_state, self.reviewer.get("detail"))
        if not isinstance(data, dict) or mtime is None:
            self.reviewer, state = {}, "not_installed"
        else:
            self.reviewer = data
            if time.time() - mtime > OFFLINE_AFTER:
                state = "offline"
            elif not data.get("logged_in"):
                state = "no_login"
            elif data.get("state") == "running":
                state = "running"
            elif data.get("state") == "error":
                state = "error"
            else:
                state = "ready"
        if not self.enabled:
            state = "disabled"
        self.reviewer_state = state
        return before != (state, self.reviewer.get("detail"))

    async def _async_take_response(self, response: Any) -> bool:
        if not isinstance(response, dict) or not isinstance(response.get("id"), str):
            return False
        store = self.hub.store
        row = await self.hass.async_add_executor_job(store.get_review, response["id"])
        if row is None or (row["status"] == "ok" and row["finished"]):
            return False  # not ours, or already taken
        review, error, status = None, response.get("error"), "error"
        if response.get("status") == "ok":
            try:
                review = parse_review(response.get("review"))
                status, error = "ok", None
            except ReviewError as err:
                error = f"The review could not be used: {err}"
        meta = {
            k: response.get(k)
            for k in ("started", "finished", "duration_ms", "cost_usd", "num_turns",
                      "reviewer_version", "claude_code_version")
        }
        await self.hass.async_add_executor_job(
            store.complete_review,
            response["id"],
            int(time.time()),
            status,
            json.dumps(review) if review else None,
            (str(error)[:1000] if error else None),
            json.dumps(meta),
        )
        await self.hass.async_add_executor_job(self._clear_request, response["id"])
        what = "Longevity review" if response["id"].startswith(LONGEVITY_PREFIX) else "Daily review"
        if status == "ok":
            _LOGGER.info("%s %s received", what, response["id"])
        else:
            _LOGGER.warning("%s %s failed: %s", what, response["id"], error)
        await self._async_load()
        if what == "Daily review" and self.longevity_due():
            # The monthly review follows a finished daily one, so the two never collide.
            try:
                await self.async_request_longevity("monthly")
            except ReviewError:
                pass
        return True

    def _clear_request(self, review_id: str) -> None:
        """Remove an answered request, so a reinstalled add-on doesn't run it again."""
        path = self.dir / "request.json"
        found = _read_json(path)
        if found and isinstance(found[1], dict) and found[1].get("id") == review_id:
            path.unlink(missing_ok=True)

    async def _async_check_overdue(self) -> bool:
        changed = False
        for a in (self.last_attempt, self.lon_attempt):
            if not a or a["status"] != "pending" or time.time() - a["requested"] < GIVE_UP_AFTER:
                continue
            await self.hass.async_add_executor_job(
                self.hub.store.complete_review,
                a["id"], int(time.time()), "error", None,
                "No answer from the Health Hub Reviewer add-on. Is it installed and running?", None,
            )
            changed = True
        if changed:
            await self._async_load()
        return changed

    @callback
    def _changed(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_REVIEW)

    # ------------------------------------------------------------- read back

    def as_dict(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        return {
            "id": row["id"],
            "day": row["day"],
            "requested": dt_util.utc_from_timestamp(row["requested"]).isoformat(),
            "finished": dt_util.utc_from_timestamp(row["finished"]).isoformat()
            if row.get("finished")
            else None,
            "reason": row.get("reason"),
            "status": row["status"],
            "error": row.get("error"),
            "review": json.loads(row["review_json"]) if row.get("review_json") else None,
            "summary": json.loads(row["summary_json"]) if row.get("summary_json") else None,
            "meta": json.loads(row["meta_json"]) if row.get("meta_json") else None,
        }

    def overview(self, kind: str = "daily") -> dict[str, Any]:
        lon = kind == "longevity"
        return {
            "enabled": self.enabled,
            "kind": kind,
            "reviewer": {"state": self.reviewer_state, **self.reviewer},
            "latest": self.as_dict(self.lon_latest if lon else self.latest),
            "last_attempt": self.as_dict(self.lon_attempt if lon else self.last_attempt),
        }
