"""Health Hub's own SQLite store, kept in the Home Assistant config folder.

Two kinds of data live here:

* Detail tables (minute samples, sleep stages, spot checks, battery) are
  pruned after the retention period (90 days by default).
* Summary tables (hourly aggregates, daily summaries, sleep sessions, workouts)
  are kept for good, and feed Home Assistant's long-term statistics.

Pure Python: no Home Assistant imports. All methods are blocking and must be
run in an executor from Home Assistant's event loop.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
HOUR = 3600

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS devices (
    device_id INTEGER PRIMARY KEY,
    name TEXT, manufacturer TEXT, type_name TEXT, model TEXT,
    last_seen INTEGER
);

CREATE TABLE IF NOT EXISTS minute_samples (
    device_id INTEGER NOT NULL, ts INTEGER NOT NULL,
    steps INTEGER, heart_rate INTEGER, stress INTEGER, spo2 INTEGER,
    distance_cm INTEGER, active_calories INTEGER,
    raw_kind INTEGER, raw_intensity INTEGER,
    PRIMARY KEY (device_id, ts)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS minute_samples_ts ON minute_samples (ts);

CREATE TABLE IF NOT EXISTS hourly (
    hour_ts INTEGER PRIMARY KEY,
    steps INTEGER, distance_m REAL, active_calories INTEGER,
    hr_mean REAL, hr_min INTEGER, hr_max INTEGER, hr_n INTEGER,
    stress_mean REAL, stress_min INTEGER, stress_max INTEGER, stress_n INTEGER,
    spo2_mean REAL, spo2_min INTEGER, spo2_max INTEGER, spo2_n INTEGER,
    source TEXT
);

CREATE TABLE IF NOT EXISTS daily_summary (
    device_id INTEGER NOT NULL, ts INTEGER NOT NULL, tz_offset_min INTEGER,
    steps INTEGER, hr_resting INTEGER, hr_min INTEGER, hr_max INTEGER,
    hr_avg INTEGER, stress_avg INTEGER, stress_min INTEGER, stress_max INTEGER,
    spo2_avg INTEGER, spo2_min INTEGER, spo2_max INTEGER, standing INTEGER,
    calories INTEGER, active_calories INTEGER, training_load_day INTEGER,
    training_load_week INTEGER, vitality INTEGER, recovery_hours INTEGER,
    PRIMARY KEY (device_id, ts)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS sleep_sessions (
    device_id INTEGER NOT NULL, ts INTEGER NOT NULL, wakeup_ts INTEGER,
    is_awake INTEGER, total_min INTEGER, deep_min INTEGER, light_min INTEGER,
    rem_min INTEGER, awake_min INTEGER,
    PRIMARY KEY (device_id, ts)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS sleep_stages (
    device_id INTEGER NOT NULL, ts INTEGER NOT NULL, stage INTEGER,
    PRIMARY KEY (device_id, ts)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS manual_samples (
    device_id INTEGER NOT NULL, ts INTEGER NOT NULL, type INTEGER, value INTEGER,
    PRIMARY KEY (device_id, ts)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS battery (
    device_id INTEGER NOT NULL, ts INTEGER NOT NULL, battery_index INTEGER NOT NULL,
    level INTEGER,
    PRIMARY KEY (device_id, ts, battery_index)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS workouts (
    device_id INTEGER NOT NULL, workout_id INTEGER NOT NULL, ts INTEGER NOT NULL,
    end_ts INTEGER, kind INTEGER, name TEXT, summary_json TEXT,
    PRIMARY KEY (device_id, workout_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS sync_state (
    table_name TEXT PRIMARY KEY,
    cursor_ts INTEGER, last_batch INTEGER, rows_total INTEGER
);
"""

# Which store table and key columns each normalised kind goes into.
_TARGETS: dict[str, tuple[str, tuple[str, ...]]] = {
    "minute": ("minute_samples", ("device_id", "ts")),
    "daily": ("daily_summary", ("device_id", "ts")),
    "sleep_session": ("sleep_sessions", ("device_id", "ts")),
    "sleep_stage": ("sleep_stages", ("device_id", "ts")),
    "manual": ("manual_samples", ("device_id", "ts")),
    "battery": ("battery", ("device_id", "ts", "battery_index")),
    "workout": ("workouts", ("device_id", "workout_id")),
}

# Tables pruned after the retention period.
_DETAIL_TABLES = ("minute_samples", "sleep_stages", "manual_samples", "battery")

# Metrics the dashboard can ask for at full detail.
SAMPLE_METRICS = {
    "heart_rate": ("minute_samples", "heart_rate"),
    "stress": ("minute_samples", "stress"),
    "spo2": ("minute_samples", "spo2"),
    "steps": ("minute_samples", "steps"),
    "sleep_stage": ("sleep_stages", "stage"),
    "battery": ("battery", "level"),
}


@dataclass
class IngestResult:
    """What changed as a result of one batch."""

    rows: int = 0
    max_ts: int | None = None
    min_ts: int | None = None
    hours: set[int] = field(default_factory=set)


def hour_start(ts: int) -> int:
    return ts - ts % HOUR


class Store:
    """Thread-safe wrapper around one SQLite file."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self._path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock, self._db:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(_SCHEMA)
            self._db.execute(
                "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ------------------------------------------------------------------ writes

    def upsert_devices(self, devices: Iterable[dict[str, Any]]) -> None:
        now = int(time.time())
        with self._lock, self._db:
            for d in devices:
                self._db.execute(
                    "INSERT INTO devices (device_id, name, manufacturer, type_name, model, last_seen)"
                    " VALUES (:device_id, :name, :manufacturer, :type_name, :model, :now)"
                    " ON CONFLICT(device_id) DO UPDATE SET name=excluded.name,"
                    " manufacturer=excluded.manufacturer, type_name=excluded.type_name,"
                    " model=excluded.model, last_seen=excluded.last_seen",
                    {**d, "now": now},
                )

    def ingest(self, kind: str, rows: list[dict[str, Any]]) -> IngestResult:
        """Insert or replace normalised rows. Re-sending the same rows is harmless."""
        result = IngestResult()
        if not rows or kind not in _TARGETS:
            return result
        table, _keys = _TARGETS[kind]
        columns = list(rows[0].keys())
        sql = (
            f"INSERT OR REPLACE INTO {table} ({', '.join(columns)})"
            f" VALUES ({', '.join(':' + c for c in columns)})"
        )
        with self._lock, self._db:
            self._db.executemany(sql, rows)
        result.rows = len(rows)
        stamps = [r["ts"] for r in rows]
        result.min_ts, result.max_ts = min(stamps), max(stamps)
        if kind == "minute":
            result.hours = {hour_start(ts) for ts in stamps}
            self.recompute_hours(result.hours)
        return result

    def recompute_hours(self, hours: Iterable[int]) -> None:
        """Rebuild hourly aggregates from minute samples for the given hours.

        Hours with no minute samples left (already pruned) are not touched, so
        the long-term record survives the retention clean-up.
        """
        hours = sorted(set(hours))
        if not hours:
            return
        with self._lock, self._db:
            for h in hours:
                row = self._db.execute(
                    """
                    SELECT COUNT(*) AS n,
                        SUM(steps) AS steps, SUM(distance_cm) AS distance_cm,
                        SUM(active_calories) AS active_calories,
                        AVG(heart_rate) AS hr_mean, MIN(heart_rate) AS hr_min,
                        MAX(heart_rate) AS hr_max, COUNT(heart_rate) AS hr_n,
                        AVG(stress) AS stress_mean, MIN(stress) AS stress_min,
                        MAX(stress) AS stress_max, COUNT(stress) AS stress_n,
                        AVG(spo2) AS spo2_mean, MIN(spo2) AS spo2_min,
                        MAX(spo2) AS spo2_max, COUNT(spo2) AS spo2_n
                    FROM minute_samples WHERE ts >= ? AND ts < ?
                    """,
                    (h, h + HOUR),
                ).fetchone()
                if not row["n"]:
                    continue
                self._db.execute(
                    """
                    INSERT OR REPLACE INTO hourly (hour_ts, steps, distance_m,
                        active_calories, hr_mean, hr_min, hr_max, hr_n,
                        stress_mean, stress_min, stress_max, stress_n,
                        spo2_mean, spo2_min, spo2_max, spo2_n, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'band')
                    """,
                    (
                        h,
                        row["steps"] or 0,
                        (row["distance_cm"] or 0) / 100.0,
                        row["active_calories"] or 0,
                        row["hr_mean"], row["hr_min"], row["hr_max"], row["hr_n"],
                        row["stress_mean"], row["stress_min"], row["stress_max"], row["stress_n"],
                        row["spo2_mean"], row["spo2_min"], row["spo2_max"], row["spo2_n"],
                    ),
                )

    def purge_detail(self, older_than_ts: int) -> int:
        """Delete detail rows older than the cut-off. Returns rows removed."""
        removed = 0
        with self._lock, self._db:
            for table in _DETAIL_TABLES:
                cur = self._db.execute(f"DELETE FROM {table} WHERE ts < ?", (older_than_ts,))
                removed += cur.rowcount
        return removed

    def get_cursor(self, table_name: str) -> int | None:
        with self._lock:
            row = self._db.execute(
                "SELECT cursor_ts FROM sync_state WHERE table_name = ?", (table_name,)
            ).fetchone()
        return row["cursor_ts"] if row else None

    def advance_cursor(self, table_name: str, max_ts: int | None, rows: int) -> None:
        """Record what HA has received. The cursor only ever moves forward."""
        now = int(time.time())
        with self._lock, self._db:
            self._db.execute(
                """
                INSERT INTO sync_state (table_name, cursor_ts, last_batch, rows_total)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(table_name) DO UPDATE SET
                    cursor_ts = MAX(COALESCE(cursor_ts, 0), COALESCE(excluded.cursor_ts, 0)),
                    last_batch = excluded.last_batch,
                    rows_total = COALESCE(rows_total, 0) + excluded.rows_total
                """,
                (table_name, max_ts, now, rows),
            )

    # ------------------------------------------------------------------ reads

    def hourly_since(self, start_hour: int) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(
                "SELECT * FROM hourly WHERE hour_ts >= ? ORDER BY hour_ts", (start_hour,)
            ).fetchall()

    def hourly_sum_before(self, hour_ts: int, column: str) -> float:
        """Total of a summed column for every hour before the given hour."""
        if column not in ("steps", "distance_m", "active_calories"):
            raise ValueError(column)
        with self._lock:
            row = self._db.execute(
                f"SELECT COALESCE(SUM({column}), 0) AS total FROM hourly WHERE hour_ts < ?",
                (hour_ts,),
            ).fetchone()
        return float(row["total"])

    def daily_since(self, start_ts: int) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(
                "SELECT * FROM daily_summary WHERE ts >= ? ORDER BY ts", (start_ts,)
            ).fetchall()

    def sleep_sessions_since(self, start_ts: int) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(
                "SELECT * FROM sleep_sessions WHERE ts >= ? ORDER BY ts", (start_ts,)
            ).fetchall()

    def totals_between(self, start_ts: int, end_ts: int) -> dict[str, Any]:
        """Steps, distance and active calories between two times, from minute samples."""
        with self._lock:
            row = self._db.execute(
                """
                SELECT COALESCE(SUM(steps), 0) AS steps,
                       COALESCE(SUM(distance_cm), 0) AS distance_cm,
                       COALESCE(SUM(active_calories), 0) AS active_calories,
                       AVG(stress) AS stress_avg, COUNT(*) AS minutes
                FROM minute_samples WHERE ts >= ? AND ts < ?
                """,
                (start_ts, end_ts),
            ).fetchone()
        return dict(row)

    def latest_value(self, metric: str) -> tuple[int, int] | None:
        """Most recent (timestamp, value) for a sample metric, ignoring gaps."""
        table, column = SAMPLE_METRICS[metric]
        with self._lock:
            row = self._db.execute(
                f"SELECT ts, {column} AS v FROM {table} WHERE {column} IS NOT NULL"
                " ORDER BY ts DESC LIMIT 1"
            ).fetchone()
        return (row["ts"], row["v"]) if row else None

    def latest_daily(self, column: str) -> tuple[int, int] | None:
        """Most recent day (start timestamp, value) that has a value for this column."""
        if column not in ("hr_resting", "vitality", "steps", "standing", "calories"):
            raise ValueError(column)
        with self._lock:
            row = self._db.execute(
                f"SELECT ts, {column} AS v FROM daily_summary WHERE {column} IS NOT NULL"
                " ORDER BY ts DESC LIMIT 1"
            ).fetchone()
        return (row["ts"], row["v"]) if row else None

    def latest_row(self, table: str) -> dict[str, Any] | None:
        if table not in ("daily_summary", "sleep_sessions", "workouts", "battery"):
            raise ValueError(table)
        with self._lock:
            row = self._db.execute(
                f"SELECT * FROM {table} ORDER BY ts DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def latest_sample_ts(self) -> int | None:
        with self._lock:
            row = self._db.execute("SELECT MAX(ts) AS ts FROM minute_samples").fetchone()
        return row["ts"]

    def samples(self, metric: str, start_ts: int, end_ts: int) -> list[tuple[int, int]]:
        """Full-detail readings for charts, skipping gaps."""
        table, column = SAMPLE_METRICS[metric]
        with self._lock:
            rows = self._db.execute(
                f"SELECT ts, {column} AS v FROM {table}"
                f" WHERE ts >= ? AND ts < ? AND {column} IS NOT NULL ORDER BY ts",
                (start_ts, end_ts),
            ).fetchall()
        return [(r["ts"], r["v"]) for r in rows]

    def sync_state(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM sync_state").fetchall()
        return {r["table_name"]: dict(r) for r in rows}
