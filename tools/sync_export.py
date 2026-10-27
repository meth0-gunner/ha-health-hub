#!/usr/bin/env python3
"""Send a Gadgetbridge database export to Home Assistant's Health Hub.

This does exactly what the phone app does, so it is useful for testing, for a
one-off backfill from a PC, or as a manual fallback if the app is broken.

    python3 sync_export.py --db Gadgetbridge --url http://homeassistant.local:8123

The access token is read from the HA_TOKEN environment variable (create a
long-lived access token on your Home Assistant profile page). Standard library
only; Python 3.9 or newer.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.request
from typing import Any, Callable, Iterator

PROTOCOL_VERSION = 1


def table_columns(db: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in db.execute(f'PRAGMA table_info("{table}")')]


def read_devices(db: sqlite3.Connection, plan: dict[str, Any]) -> list[dict[str, Any]]:
    spec = plan["device_table"]
    present = table_columns(db, spec["name"])
    cols = [c for c in spec["columns"] if c in present]
    if not cols:
        return []
    quoted = ", ".join('"' + c + '"' for c in cols)
    sql = f'SELECT {quoted} FROM "{spec["name"]}"'
    return [dict(zip(cols, row)) for row in db.execute(sql)]


def read_batches(
    db: sqlite3.Connection, table: dict[str, Any], max_rows: int
) -> Iterator[tuple[list[str], list[list[Any]]]]:
    """Yield (columns, rows) batches for one table in the plan, oldest first.

    Columns HA asks for but this Gadgetbridge version lacks are skipped; HA
    treats them as missing. Rows sharing a timestamp are paged with an offset so
    none are skipped at a batch boundary.
    """
    present = table_columns(db, table["name"])
    ts_col = table["ts_column"]
    if not present or ts_col not in present:
        return
    cols = [c for c in table["columns"] if c in present]
    order = [ts_col] + [c for c in ("DEVICE_ID", "BATTERY_INDEX", "_id") if c in cols and c != ts_col]
    q = lambda c: f'"{c}"'  # noqa: E731
    sql = (
        f'SELECT {", ".join(map(q, cols))} FROM "{table["name"]}"'
        f" WHERE {q(ts_col)} >= ? ORDER BY {', '.join(map(q, order))} LIMIT ? OFFSET ?"
    )
    ts_index = cols.index(ts_col)
    since, offset = table["since"], 0
    while True:
        rows = [list(r) for r in db.execute(sql, (since, max_rows, offset))]
        if not rows:
            return
        yield cols, rows
        if len(rows) < max_rows:
            return
        last = rows[-1][ts_index]
        same = sum(1 for r in rows if r[ts_index] == last)
        offset = offset + same if last == since else same
        since = last


def sync(
    db_path: str,
    get_plan: Callable[[], dict[str, Any]],
    post_batch: Callable[[dict[str, Any]], dict[str, Any]],
    app_version: str = "sync_export",
) -> dict[str, int]:
    """Run one sync. Returns rows sent per table."""
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        plan = get_plan()
        if plan.get("protocol") != PROTOCOL_VERSION:
            raise RuntimeError(f"Home Assistant speaks protocol {plan.get('protocol')}")
        devices = read_devices(db, plan)
        sent: dict[str, int] = {}
        for table in plan["tables"]:
            for cols, rows in read_batches(db, table, plan["max_rows"]):
                post_batch(
                    {
                        "protocol": PROTOCOL_VERSION,
                        "app_version": app_version,
                        "table": table["name"],
                        "columns": cols,
                        "rows": rows,
                        "devices": devices,
                    }
                )
                sent[table["name"]] = sent.get(table["name"], 0) + len(rows)
        return sent
    finally:
        db.close()


def _http(url: str, token: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method="POST" if data else "GET",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", required=True, help="Gadgetbridge export file")
    parser.add_argument("--url", required=True, help="Home Assistant URL")
    args = parser.parse_args()
    token = os.environ.get("HA_TOKEN")
    if not token:
        print("Set HA_TOKEN to a long-lived access token.", file=sys.stderr)
        return 2
    base = args.url.rstrip("/") + "/api/health_hub/sync"
    sent = sync(
        args.db,
        lambda: _http(base + "/plan", token),
        lambda batch: _http(base + "/batch", token, batch),
    )
    for name, count in sent.items():
        print(f"{name}: {count} rows")
    if not sent:
        print("Nothing new to send.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
