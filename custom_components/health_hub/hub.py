"""Health Hub runtime: receives batches, keeps statistics and sensors current."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import (
    CONF_OVERLAP_HOURS,
    CONF_RETENTION_DAYS,
    DEFAULT_OVERLAP_HOURS,
    DEFAULT_RETENTION_DAYS,
    DOMAIN,
    SIGNAL_UPDATED,
    STORE_FILE,
)
from .core.history import History
from .core.protocol import Batch, build_plan, parse_batch
from .core.stats import STATS_BY_KEY, rows_for_change, rows_for_full_rebuild
from .core.store import Store

_LOGGER = logging.getLogger(__name__)


@dataclass
class Snapshot:
    """Everything the sensors show, computed in one go."""

    steps_today: int | None = None
    distance_today_km: float | None = None
    active_calories_today: int | None = None
    stress_today: float | None = None
    heart_rate: tuple[int, int] | None = None  # (ts, bpm)
    spo2: tuple[int, int] | None = None
    stress: tuple[int, int] | None = None
    battery: tuple[int, int] | None = None
    resting_hr: tuple[int, int] | None = None  # (day start ts, bpm)
    vitality: tuple[int, int] | None = None
    sleep: dict[str, Any] | None = None
    last_reading_ts: int | None = None
    last_sync: datetime | None = None
    sync_state: dict[str, Any] = field(default_factory=dict)


class HealthHub:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, store: Store) -> None:
        self.hass = hass
        self.entry = entry
        self.store = store
        self.snapshot = Snapshot()
        self._lock = asyncio.Lock()

    @property
    def retention_days(self) -> int:
        return self.entry.options.get(CONF_RETENTION_DAYS, DEFAULT_RETENTION_DAYS)

    @property
    def overlap_hours(self) -> int:
        return self.entry.options.get(CONF_OVERLAP_HOURS, DEFAULT_OVERLAP_HOURS)

    @classmethod
    async def async_create(cls, hass: HomeAssistant, entry: ConfigEntry) -> HealthHub:
        store = await hass.async_add_executor_job(Store, hass.config.path(STORE_FILE))
        hub = cls(hass, entry, store)
        await hub.async_refresh()
        return hub

    async def async_close(self) -> None:
        await self.hass.async_add_executor_job(self.store.close)

    # ------------------------------------------------------------------ sync

    async def async_plan(self) -> dict[str, Any]:
        return await self.hass.async_add_executor_job(
            build_plan, self.store, self.overlap_hours
        )

    async def async_ingest(self, payload: Any) -> dict[str, Any]:
        """Store one batch from the phone. Raises ProtocolError on bad input."""
        batch: Batch = parse_batch(payload)
        async with self._lock:
            result = await self.hass.async_add_executor_job(self._ingest_blocking, batch)
            if result.rows:
                await self._async_write_statistics(batch.spec.kind, result.min_ts)
        await self.async_refresh()
        cursor = await self.hass.async_add_executor_job(self.store.get_cursor, batch.spec.name)
        return {"accepted": result.rows, "received": batch.raw_count, "cursor": cursor}

    def _ingest_blocking(self, batch: Batch):
        if batch.devices:
            self.store.upsert_devices(batch.devices)
        result = self.store.ingest(batch.spec.kind, batch.rows)
        self.store.advance_cursor(batch.spec.name, batch.max_ts, batch.raw_count)
        return result

    # ------------------------------------------------------------ statistics

    async def _async_write_statistics(self, kind: str, min_ts: int | None) -> None:
        if min_ts is None:
            return
        tz = dt_util.get_default_time_zone()
        rows = await self.hass.async_add_executor_job(
            rows_for_change, self.store, kind, min_ts, tz
        )
        self._submit_statistics(rows)

    async def async_import_history(self, history: History) -> dict[str, int]:
        """Store imported history (e.g. Fitbit) and rewrite every statistic."""
        async with self._lock:
            counts = await self.hass.async_add_executor_job(self.store.import_history, history)
        await self.async_rebuild_statistics()
        await self.async_refresh()
        _LOGGER.info("Imported %s history: %s", history.source, counts)
        return counts

    async def async_rebuild_statistics(self) -> None:
        """Rewrite every statistic from the store (service call)."""
        tz = dt_util.get_default_time_zone()
        async with self._lock:
            rows = await self.hass.async_add_executor_job(rows_for_full_rebuild, self.store, tz)
            self._submit_statistics(rows)

    def _submit_statistics(self, rows_by_key: dict[str, list[dict[str, Any]]]) -> None:
        for key, rows in rows_by_key.items():
            stat = STATS_BY_KEY[key]
            metadata = StatisticMetaData(
                mean_type=StatisticMeanType.NONE
                if stat.kind == "sum"
                else StatisticMeanType.ARITHMETIC,
                has_sum=stat.kind == "sum",
                name=stat.name,
                source=DOMAIN,
                statistic_id=f"{DOMAIN}:{stat.key}",
                unit_class=None,
                unit_of_measurement=stat.unit,
            )
            async_add_external_statistics(
                self.hass, metadata, [StatisticData(**r) for r in rows]
            )

    # ----------------------------------------------------------- maintenance

    async def async_purge(self) -> int:
        cutoff = int(time.time()) - self.retention_days * 86400
        removed = await self.hass.async_add_executor_job(self.store.purge_detail, cutoff)
        if removed:
            _LOGGER.debug("Removed %s detail rows older than %s days", removed, self.retention_days)
        return removed

    async def async_refresh(self) -> None:
        start = int(dt_util.start_of_local_day().timestamp())
        self.snapshot = await self.hass.async_add_executor_job(self._snapshot_blocking, start)
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)

    def _snapshot_blocking(self, day_start: int) -> Snapshot:
        s = self.store
        totals = s.totals_between(day_start, day_start + 86400)
        has_today = totals["minutes"] > 0
        sync_state = s.sync_state()
        batches = [v["last_batch"] for v in sync_state.values() if v.get("last_batch")]
        return Snapshot(
            steps_today=totals["steps"] if has_today else 0,
            distance_today_km=round(totals["distance_cm"] / 100000, 2) if has_today else 0,
            active_calories_today=totals["active_calories"] if has_today else 0,
            stress_today=round(totals["stress_avg"], 1) if totals["stress_avg"] else None,
            heart_rate=s.latest_value("heart_rate"),
            spo2=s.latest_value("spo2"),
            stress=s.latest_value("stress"),
            battery=s.latest_value("battery"),
            resting_hr=s.latest_daily("hr_resting"),
            vitality=s.latest_daily("vitality"),
            sleep=s.latest_row("sleep_sessions"),
            last_reading_ts=s.latest_sample_ts(),
            last_sync=dt_util.utc_from_timestamp(max(batches)) if batches else None,
            sync_state=sync_state,
        )
