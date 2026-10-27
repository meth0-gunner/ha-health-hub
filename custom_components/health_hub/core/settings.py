"""Goals and personal settings, kept in the store so the Health page can edit them.

Pure Python: no Home Assistant imports.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from datetime import date, time
from typing import Any

from .store import Store

META_KEY = "settings"


@dataclass
class Settings:
    steps_goal: int = 10000
    sleep_goal_min: int = 450  # 7h 30m asleep
    bed_target: str = "22:45"  # in bed by
    wake_target: str = "06:45"
    weight_goal_kg: float | None = None
    weight_goal_set: str | None = None  # date the goal was set (for "down since")
    age: int | None = None  # only used to estimate maximum heart rate
    max_hr: int | None = None  # overrides the estimate
    gym_per_week: float = 3
    compex_per_week: float = 4
    block_weeks: int = 4
    block_anchor: str | None = None  # a Monday; blocks run every block_weeks from it

    @property
    def effective_max_hr(self) -> int:
        if self.max_hr:
            return self.max_hr
        if self.age:
            return round(208 - 0.7 * self.age)  # Tanaka et al. 2001
        return 185

    @property
    def bed_minutes(self) -> int:
        t = time.fromisoformat(self.bed_target)
        return t.hour * 60 + t.minute

    @property
    def wake_minutes(self) -> int:
        t = time.fromisoformat(self.wake_target)
        return t.hour * 60 + t.minute


RANGES: dict[str, tuple[float, float]] = {
    "steps_goal": (500, 50000),
    "sleep_goal_min": (240, 720),
    "weight_goal_kg": (30, 300),
    "age": (10, 110),
    "max_hr": (100, 230),
    "gym_per_week": (0.5, 14),
    "compex_per_week": (0.5, 14),
    "block_weeks": (1, 12),
}


class SettingsError(ValueError):
    pass


def load(store: Store) -> Settings:
    raw = store.get_meta(META_KEY)
    data = json.loads(raw) if raw else {}
    known = {f.name for f in fields(Settings)}
    return Settings(**{k: v for k, v in data.items() if k in known})


def update(store: Store, changes: dict[str, Any]) -> Settings:
    """Validate and save changes; returns the new settings. Raises SettingsError."""
    current = asdict(load(store))
    known = {f.name: f for f in fields(Settings)}
    for key, value in changes.items():
        if key not in known:
            raise SettingsError(f"unknown setting {key}")
        if value in ("", None):
            if known[key].default is None:
                current[key] = None
                continue
            raise SettingsError(f"{key} can't be empty")
        if key in ("bed_target", "wake_target"):
            try:
                t = time.fromisoformat(str(value))
            except ValueError as err:
                raise SettingsError(f"{key} must be a time like 22:45") from err
            value = f"{t.hour:02d}:{t.minute:02d}"
        elif key in ("weight_goal_set", "block_anchor"):
            try:
                d = date.fromisoformat(str(value))
            except ValueError as err:
                raise SettingsError(f"{key} must be a date") from err
            if key == "block_anchor" and d.weekday() != 0:
                raise SettingsError("blocks start on a Monday")
            value = d.isoformat()
        else:
            try:
                value = float(value)
            except (TypeError, ValueError) as err:
                raise SettingsError(f"{key} must be a number") from err
            low, high = RANGES[key]
            if not low <= value <= high:
                raise SettingsError(f"{key} must be between {low:g} and {high:g}")
            if key not in ("weight_goal_kg", "gym_per_week", "compex_per_week"):
                value = int(round(value))
        current[key] = value
    store.set_meta(META_KEY, json.dumps(current))
    return Settings(**current)
