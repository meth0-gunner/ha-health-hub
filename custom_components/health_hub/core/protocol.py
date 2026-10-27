"""The sync protocol between the phone app and Home Assistant.

1. The app asks HA for a sync plan: which tables and columns to read, and from
   what timestamp. HA owns the cursor, so if HA is restored from a backup the
   app simply re-sends what is missing.
2. The app reads those rows from Gadgetbridge's latest export and posts them
   in batches. HA confirms each batch; only then does its cursor move.

Each plan starts a little before the cursor (the overlap), because Gadgetbridge
rewrites some rows in place, such as today's daily summary.

Pure Python: no Home Assistant imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .gadgetbridge import (
    DEVICE_COLUMNS,
    DEVICE_TABLE,
    TABLES,
    TABLES_BY_NAME,
    TableSpec,
    from_seconds,
    normalise_device,
    normalise_row,
    to_seconds,
)
from .store import Store

PROTOCOL_VERSION = 1
MAX_ROWS_PER_BATCH = 5000


class ProtocolError(ValueError):
    """The app sent something HA cannot accept."""


def build_plan(store: Store, overlap_hours: int) -> dict[str, Any]:
    tables = []
    for spec in TABLES:
        cursor = store.get_cursor(spec.name)
        since = 0 if cursor is None else max(0, cursor - overlap_hours * 3600)
        tables.append(
            {
                "name": spec.name,
                "ts_column": spec.ts_column,
                "ts_unit": spec.ts_unit,
                "columns": list(spec.columns),
                "since": from_seconds(since, spec.ts_unit),
            }
        )
    return {
        "protocol": PROTOCOL_VERSION,
        "max_rows": MAX_ROWS_PER_BATCH,
        "device_table": {"name": DEVICE_TABLE, "columns": list(DEVICE_COLUMNS)},
        "tables": tables,
    }


@dataclass
class Batch:
    spec: TableSpec
    rows: list[dict[str, Any]]  # normalised
    raw_count: int
    max_ts: int | None  # epoch seconds, from the raw rows
    devices: list[dict[str, Any]]


def _rows_as_dicts(columns: list[str], rows: list[list[Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if not isinstance(row, list) or len(row) != len(columns):
            raise ProtocolError("each row must be a list matching 'columns'")
        out.append(dict(zip(columns, row)))
    return out


def parse_batch(payload: Any) -> Batch:
    if not isinstance(payload, dict):
        raise ProtocolError("body must be a JSON object")
    if payload.get("protocol") != PROTOCOL_VERSION:
        raise ProtocolError(f"unsupported protocol {payload.get('protocol')!r}")

    spec = TABLES_BY_NAME.get(payload.get("table"))
    if spec is None:
        raise ProtocolError(f"unknown table {payload.get('table')!r}")

    columns = payload.get("columns")
    rows = payload.get("rows")
    if not isinstance(columns, list) or not all(isinstance(c, str) for c in columns):
        raise ProtocolError("'columns' must be a list of names")
    if not isinstance(rows, list):
        raise ProtocolError("'rows' must be a list")
    if len(rows) > MAX_ROWS_PER_BATCH:
        raise ProtocolError(f"too many rows (max {MAX_ROWS_PER_BATCH})")
    if spec.ts_column not in columns:
        raise ProtocolError(f"'columns' must include {spec.ts_column}")

    raw = _rows_as_dicts(columns, rows)
    allowed = set(spec.columns)
    for r in raw:  # drop anything HA did not ask for
        for key in list(r):
            if key not in allowed:
                del r[key]

    normalised = [n for n in (normalise_row(spec, r) for r in raw) if n is not None]
    stamps = [to_seconds(r.get(spec.ts_column), spec.ts_unit) for r in raw]
    stamps = [s for s in stamps if s is not None]

    devices: list[dict[str, Any]] = []
    dev_payload = payload.get("devices") or []
    if isinstance(dev_payload, list):
        for d in dev_payload:
            if isinstance(d, dict):
                n = normalise_device({k: d.get(k) for k in DEVICE_COLUMNS})
                if n:
                    devices.append(n)

    return Batch(
        spec=spec,
        rows=normalised,
        raw_count=len(raw),
        max_ts=max(stamps) if stamps else None,
        devices=devices,
    )
