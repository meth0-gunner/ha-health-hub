"""Build synthetic Gadgetbridge exports with the real table definitions."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).parent / "fixtures" / "gadgetbridge_schema.sql"

# 2026-10-26 00:00 in Sydney (UTC+11), as Gadgetbridge stores it.
DAY0 = 1792933200


def make_export(path: Path, minutes: int = 180, start: int = DAY0 + 7 * 3600) -> Path:
    db = sqlite3.connect(path)
    db.executescript(SCHEMA.read_text())
    db.execute(
        "INSERT INTO DEVICE VALUES (1, 'Xiaomi Smart Band 8 Pro 0000', 'Xiaomi',"
        " 'AA:BB:CC:DD:EE:FF', 0, 'MIBAND8PRO', 'M2333B1', NULL, NULL)"
    )
    db.execute("INSERT INTO USER VALUES (1, 'Private Name', 0, 1)")
    for i in range(minutes):
        ts = start + i * 60
        worn = i % 10 != 0  # every tenth minute: no readings, like an unworn band
        db.execute(
            "INSERT INTO XIAOMI_ACTIVITY_SAMPLE VALUES (?, 1, 1, 10, ?, 1, ?, ?, ?, ?, ?, -1)",
            (
                ts,
                20 if worn else 0,
                70 + i % 5 if worn else 0,
                30 if worn else 0,
                97 if worn else 0,
                1500 if worn else 0,
                2 if worn else 0,
            ),
        )
    db.execute(
        "INSERT INTO XIAOMI_DAILY_SUMMARY_SAMPLE (TIMESTAMP, DEVICE_ID, USER_ID, TIMEZONE,"
        " STEPS, HR_RESTING, HR_AVG, VITALITY_CURRENT) VALUES (?, 1, 1, 44, 3240, 58, 71, 12)",
        (DAY0 * 1000,),
    )
    # Slept 22:30 to 06:30, credited to the morning of DAY0.
    bed = DAY0 - 90 * 60
    db.execute(
        "INSERT INTO XIAOMI_SLEEP_TIME_SAMPLE VALUES (?, 1, 1, ?, 0, 480, 90, 270, 100, 20)",
        (bed * 1000, (DAY0 + 6.5 * 3600) * 1000),
    )
    for i, stage in enumerate((2, 3, 4, 5, 3)):
        db.execute(
            "INSERT INTO XIAOMI_SLEEP_STAGE_SAMPLE VALUES (?, 1, 1, ?)",
            ((bed + i * 1800) * 1000, stage),
        )
    # Battery timestamps are in seconds, unlike the other non-activity tables.
    db.execute("INSERT INTO BATTERY_LEVEL VALUES (?, 1, 87, 0)", (start + 3600,))
    db.execute(
        "INSERT INTO BASE_ACTIVITY_SUMMARY (_id, NAME, START_TIME, END_TIME,"
        " OVERRIDE_ACTIVITY_KIND, ACTIVITY_KIND, BASE_LATITUDE, BASE_LONGITUDE,"
        " DEVICE_ID, USER_ID, SUMMARY_DATA) VALUES (1, 'Walk', ?, ?, 0, 1, -35000000,"
        " 149000000, 1, 1, '{}')",
        ((start + 600) * 1000, (start + 2400) * 1000),
    )
    db.commit()
    db.close()
    return path
