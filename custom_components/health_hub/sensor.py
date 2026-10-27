"""Health Hub sensors: today's totals and latest readings.

These sensors have no state class on purpose: their values arrive late and in
batches, so Home Assistant's own statistics would be stamped with the wrong
times. Long-term charts use the `health_hub:*` statistics instead, which are
written on the times the data actually happened.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import HealthHubConfigEntry
from .const import DOMAIN, NAME, SIGNAL_REVIEW, SIGNAL_UPDATED
from .core.review import attention_label
from .hub import Snapshot


def _ts(value: int | None) -> datetime | None:
    return dt_util.utc_from_timestamp(value) if value else None


def _reading(pair: tuple[int, int] | None) -> Any:
    return pair[1] if pair else None


def _measured_at(pair: tuple[int, int] | None) -> dict[str, Any]:
    return {"measured_at": _ts(pair[0]).isoformat()} if pair else {}


def _day(pair: tuple[int, int] | None) -> dict[str, Any]:
    return {"date": dt_util.as_local(_ts(pair[0])).date().isoformat()} if pair else {}


def _hours(minutes: int | None) -> float | None:
    return round(minutes / 60, 2) if minutes is not None else None


def _sleep_value(s: Snapshot) -> float | None:
    return _hours(s.sleep["total_min"]) if s.sleep else None


def _sleep_attrs(s: Snapshot) -> dict[str, Any]:
    if not s.sleep:
        return {}
    sl = s.sleep
    return {
        "fell_asleep": _ts(sl["ts"]).isoformat() if sl["ts"] else None,
        "woke_up": _ts(sl["wakeup_ts"]).isoformat() if sl["wakeup_ts"] else None,
        "deep_hours": _hours(sl["deep_min"]),
        "light_hours": _hours(sl["light_min"]),
        "rem_hours": _hours(sl["rem_min"]),
        "awake_hours": _hours(sl["awake_min"]),
    }


@dataclass(frozen=True, kw_only=True)
class HealthSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Snapshot], Any]
    attrs_fn: Callable[[Snapshot], dict[str, Any]] = lambda _s: {}


SENSORS: tuple[HealthSensorDescription, ...] = (
    HealthSensorDescription(
        key="steps_today",
        name="Steps today",
        icon="mdi:shoe-print",
        native_unit_of_measurement="steps",
        value_fn=lambda s: s.steps_today,
    ),
    HealthSensorDescription(
        key="distance_today",
        name="Distance today",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=2,
        value_fn=lambda s: s.distance_today_km,
    ),
    HealthSensorDescription(
        key="active_calories_today",
        name="Active calories today",
        icon="mdi:fire",
        native_unit_of_measurement="kcal",
        value_fn=lambda s: s.active_calories_today,
    ),
    HealthSensorDescription(
        key="stress_today",
        name="Stress today",
        icon="mdi:head-heart-outline",
        suggested_display_precision=0,
        value_fn=lambda s: s.stress_today,
    ),
    HealthSensorDescription(
        key="heart_rate",
        name="Heart rate",
        icon="mdi:heart-pulse",
        native_unit_of_measurement="bpm",
        value_fn=lambda s: _reading(s.heart_rate),
        attrs_fn=lambda s: _measured_at(s.heart_rate),
    ),
    HealthSensorDescription(
        key="blood_oxygen",
        name="Blood oxygen",
        icon="mdi:water-percent",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda s: _reading(s.spo2),
        attrs_fn=lambda s: _measured_at(s.spo2),
    ),
    HealthSensorDescription(
        key="stress",
        name="Stress",
        icon="mdi:head-heart-outline",
        value_fn=lambda s: _reading(s.stress),
        attrs_fn=lambda s: _measured_at(s.stress),
    ),
    HealthSensorDescription(
        key="resting_heart_rate",
        name="Resting heart rate",
        icon="mdi:heart",
        native_unit_of_measurement="bpm",
        value_fn=lambda s: _reading(s.resting_hr),
        attrs_fn=lambda s: _day(s.resting_hr),
    ),
    HealthSensorDescription(
        key="vitality_score",
        name="Vitality score",
        icon="mdi:run",
        value_fn=lambda s: _reading(s.vitality),
        attrs_fn=lambda s: _day(s.vitality),
    ),
    HealthSensorDescription(
        key="last_sleep",
        name="Last sleep",
        icon="mdi:sleep",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=1,
        value_fn=_sleep_value,
        attrs_fn=_sleep_attrs,
    ),
    HealthSensorDescription(
        key="readiness",
        name="Readiness",
        icon="mdi:battery-heart-variant",
        value_fn=lambda s: s.readiness["score"] if s.readiness else None,
        attrs_fn=lambda s: {"rating": s.readiness["label"], "summary": s.readiness["summary"]} if s.readiness else {},
    ),
    HealthSensorDescription(
        key="day_load",
        name="Day load",
        icon="mdi:run-fast",
        value_fn=lambda s: s.day_load["score"] if s.day_load else None,
        attrs_fn=lambda s: {"recommended_low": s.day_load["range"][0], "recommended_high": s.day_load["range"][1],
                            "active_minutes": s.day_load["active_min"]} if s.day_load else {},
    ),
    HealthSensorDescription(
        key="energy",
        name="Energy",
        icon="mdi:lightning-bolt-circle",
        value_fn=lambda s: s.energy["now"] if s.energy else None,
        attrs_fn=lambda s: {"peak_today": s.energy["peak"], "note": "an estimate"} if s.energy else {},
    ),
    HealthSensorDescription(
        key="sleep_score",
        name="Sleep score",
        icon="mdi:sleep",
        value_fn=lambda s: s.sleep_score["score"] if s.sleep_score else None,
        attrs_fn=lambda s: {"rating": s.sleep_score["label"], "date": s.sleep_score["date"]} if s.sleep_score else {},
    ),
    HealthSensorDescription(
        key="rewards",
        name="Rewards to spend",
        icon="mdi:trophy-outline",
        value_fn=lambda s: s.rewards,
    ),
    HealthSensorDescription(
        key="band_battery",
        name="Band battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: _reading(s.battery),
        attrs_fn=lambda s: _measured_at(s.battery),
    ),
    HealthSensorDescription(
        key="last_sync",
        name="Last sync",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.last_sync,
    ),
    HealthSensorDescription(
        key="last_reading",
        name="Last band reading",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: _ts(s.last_reading_ts),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HealthHubConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        [*(HealthSensor(entry, d) for d in SENSORS), DailyReviewSensor(entry), ReviewerSensor(entry)]
    )


def _device(entry: HealthHubConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=NAME,
        manufacturer="Gadgetbridge",
        entry_type=DeviceEntryType.SERVICE,
    )


class HealthSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    entity_description: HealthSensorDescription

    def __init__(self, entry: HealthHubConfigEntry, description: HealthSensorDescription) -> None:
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device(entry)

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self._entry.runtime_data.snapshot)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.entity_description.attrs_fn(self._entry.runtime_data.snapshot)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATED, self._updated)
        )

    @callback
    def _updated(self) -> None:
        self.async_write_ha_state()


class _ReviewEntity(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _key = ""

    def __init__(self, entry: HealthHubConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{self._key}"
        self._attr_device_info = _device(entry)

    @property
    def _reviews(self):
        return self._entry.runtime_data.reviews

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_REVIEW, self.async_write_ha_state)
        )


class DailyReviewSensor(_ReviewEntity):
    """Today's review headline. The full review is on the Health page."""

    _key = "daily_review"
    _attr_name = "Daily review"
    _attr_icon = "mdi:text-box-check-outline"
    _unrecorded_attributes = frozenset({"summary", "suggestions"})

    @property
    def native_value(self) -> str | None:
        latest = self._reviews.latest
        if not latest or not latest.get("review_json"):
            return None
        return (self._reviews.as_dict(latest)["review"].get("headline") or "")[:255] or None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        latest = self._reviews.as_dict(self._reviews.latest)
        if not latest:
            return {}
        review = latest["review"] or {}
        return {
            "date": latest["day"],
            "generated": latest["finished"],
            "attention": attention_label(review),
            "summary": review.get("summary"),
            "suggestions": [s["text"] for s in review.get("suggestions", [])],
        }


class ReviewerSensor(_ReviewEntity):
    """Whether the Health Hub Reviewer add-on is there and signed in."""

    _key = "reviewer"
    _attr_name = "Reviewer"
    _attr_icon = "mdi:robot-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["ready", "running", "no_login", "offline", "error", "not_installed", "disabled", "unknown"]

    @property
    def native_value(self) -> str:
        return self._reviews.reviewer_state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        r = self._reviews.reviewer
        attempt = self._reviews.last_attempt
        return {
            "last_seen": r.get("alive"),
            "detail": r.get("detail"),
            "reviewer_version": r.get("reviewer_version"),
            "claude_code_version": r.get("claude_code_version"),
            "last_request": attempt["day"] if attempt else None,
            "last_request_status": attempt["status"] if attempt else None,
            "last_error": attempt.get("error") if attempt else None,
        }
