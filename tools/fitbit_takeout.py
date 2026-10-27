#!/usr/bin/env python3
"""Convert a Google Takeout of Fitbit / Google Health data into a Health Hub history file.

    python3 fitbit_takeout.py takeout-*.zip -o fitbit-history.json.gz

Then upload the output in Home Assistant: Health Hub → Configure → Import history.

Only these parts of the Takeout are read; location, GPS, messages and the rest
are ignored:

* hourly: steps, distance, heart rate, blood oxygen, active calories
* daily: resting heart rate, heart rate variability, breathing rate
* weight measurements
* sleep sessions, with stages and sleep score

Steps, distance and heart rate use the Fitbit tracker's own readings. Phone and
app sources (MobileTrack, Health Connect) are skipped, as the Fitbit app does
when a tracker is worn, so nothing is counted twice.

Standard library only; Python 3.11 or newer.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterator

FORMAT = "health_hub_history"
VERSION = 1

# Sources that are not the tracker itself. Their steps, distance and heart rate
# duplicate the tracker's on days it was worn.
NON_TRACKER_SOURCES = {
    "MobileTrack",
    "Phone Health Connect",
    "Fit Health Connect",
    "Google Health App",
}

HOURLY_COLUMNS = [
    "hour_ts", "steps", "distance_m", "active_calories",
    "hr_mean", "hr_min", "hr_max", "hr_n",
    "spo2_mean", "spo2_min", "spo2_max", "spo2_n",
]
SLEEP_COLUMNS = [
    "start_ts", "end_ts", "total_min", "deep_min", "light_min", "rem_min", "awake_min", "score",
]

ACTIVITY = "Physical Activity_GoogleData/"
FITNESS = "Health Fitness Data_GoogleData/"
PATTERNS = {
    "steps": re.compile(re.escape(ACTIVITY) + r"Steps/steps_[\d-]+\.csv$"),
    "distance": re.compile(re.escape(ACTIVITY) + r"Distance/distance_[\d-]+\.csv$"),
    "heart_rate": re.compile(re.escape(ACTIVITY) + r"Heart Rate/heart_rate_[\d-]+\.csv$"),
    "spo2": re.compile(re.escape(ACTIVITY) + r"Oxygen Saturation/oxygen_saturation_[\d-]+\.csv$"),
    "active_calories": re.compile(
        re.escape(ACTIVITY) + r"Active Energy Burned/active_energy_burned_[\d-]+\.csv$"
    ),
    "resting_hr": re.compile(re.escape(ACTIVITY) + r"Daily Resting Heart Rate/daily_resting_heart_rate\.csv$"),
    "hrv": re.compile(re.escape(ACTIVITY) + r"Daily Heart Rate Variability/daily_heart_rate_variability\.csv$"),
    "respiratory_rate": re.compile(re.escape(ACTIVITY) + r"Daily Respiratory Rate/daily_respiratory_rate\.csv$"),
    "weight": re.compile(re.escape(ACTIVITY) + r"Weight/weight\.csv$"),
    "sleeps": re.compile(re.escape(FITNESS) + r"UserSleeps_[\d-]+\.csv$"),
    "sleep_stages": re.compile(re.escape(FITNESS) + r"UserSleepStages_[\d-]+\.csv$"),
    "sleep_scores": re.compile(re.escape(FITNESS) + r"UserSleepScores_[\d-]+\.csv$"),
}


def _epoch(ts: str) -> int:
    """'2023-09-01T00:13:00Z' (UTC) to epoch seconds."""
    return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())


def _hour_epoch(hour_key: str) -> int:
    """'2023-09-01T00' to epoch seconds."""
    return int(datetime.strptime(hour_key, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc).timestamp())


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


class _Hour:
    __slots__ = ("steps", "distance", "active_kcal", "hr", "spo2")

    def __init__(self) -> None:
        self.steps = 0.0
        self.distance = 0.0
        self.active_kcal = 0.0
        self.hr: list[float] = []  # per-minute means
        self.spo2: list[float] = []


class Converter:
    def __init__(self) -> None:
        self.hours: dict[str, _Hour] = defaultdict(_Hour)
        self.daily: dict[tuple[str, str], float] = {}
        self.measurements: list[tuple[str, int, float]] = []
        self.sleeps: dict[str, dict] = {}
        self.stages: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.scores: dict[str, float] = {}
        self._stage_ids: set[str] = set()
        self.files_read = 0

    # ------------------------------------------------------------ reading

    def add_zip(self, path: str) -> None:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                for kind, pattern in PATTERNS.items():
                    if pattern.search(name):
                        with z.open(name) as raw:
                            rows = csv.DictReader(io.TextIOWrapper(raw, "utf-8", newline=""))
                            getattr(self, "_read_" + kind)(rows)
                        self.files_read += 1
                        break

    @staticmethod
    def _tracker_rows(rows: Iterator[dict]) -> Iterator[dict]:
        for row in rows:
            if row.get("data source") not in NON_TRACKER_SOURCES and row.get("timestamp"):
                yield row

    def _read_steps(self, rows) -> None:
        for row in self._tracker_rows(rows):
            self.hours[row["timestamp"][:13]].steps += _float(row["steps"]) or 0

    def _read_distance(self, rows) -> None:
        for row in self._tracker_rows(rows):
            self.hours[row["timestamp"][:13]].distance += _float(row["distance"]) or 0

    def _read_active_calories(self, rows) -> None:
        for row in rows:
            if row.get("timestamp"):
                self.hours[row["timestamp"][:13]].active_kcal += _float(row["Kilocalories"]) or 0

    def _per_minute(self, rows, column: str, low: float, high: float, tracker_only: bool):
        minutes: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
        source = self._tracker_rows(rows) if tracker_only else rows
        for row in source:
            value = _float(row.get(column))
            if value is None or not low <= value <= high:
                continue
            m = minutes[row["timestamp"][:16]]
            m[0] += value
            m[1] += 1
        return minutes

    def _read_heart_rate(self, rows) -> None:
        for minute, (total, n) in self._per_minute(rows, "beats per minute", 25, 240, True).items():
            self.hours[minute[:13]].hr.append(total / n)

    def _read_spo2(self, rows) -> None:
        for minute, (total, n) in self._per_minute(
            rows, "oxygen saturation percentage", 70, 100, False
        ).items():
            self.hours[minute[:13]].spo2.append(total / n)

    def _read_daily(self, rows, metric: str, column: str) -> None:
        for row in rows:
            value = _float(row.get(column))
            if value is not None and value > 0 and row.get("timestamp"):
                self.daily[(metric, row["timestamp"][:10])] = value

    def _read_resting_hr(self, rows) -> None:
        self._read_daily(rows, "resting_heart_rate", "beats per minute")

    def _read_hrv(self, rows) -> None:
        self._read_daily(rows, "hrv", "average heart rate variability milliseconds")

    def _read_respiratory_rate(self, rows) -> None:
        self._read_daily(rows, "respiratory_rate", "breaths per minute")

    def _read_weight(self, rows) -> None:
        for row in rows:
            grams = _float(row.get("weight grams"))
            if grams and row.get("timestamp"):
                self.measurements.append(("weight", _epoch(row["timestamp"]), round(grams / 1000, 2)))

    def _read_sleeps(self, rows) -> None:
        for row in rows:
            if not row.get("sleep_id") or not row.get("sleep_start") or not row.get("sleep_end"):
                continue
            self.sleeps[row["sleep_id"]] = {
                "type": row.get("sleep_type"),
                "start": _epoch(row["sleep_start"]),
                "end": _epoch(row["sleep_end"]),
                "asleep": _float(row.get("minutes_asleep")),
                "awake": _float(row.get("minutes_awake")),
                "algorithm": row.get("algorithm_version") or "",
                "updated": row.get("sleep_last_updated") or "",
            }

    @staticmethod
    def _rank(s: dict) -> tuple:
        """Prefer the newest analysis: sleep_session_v2 over v1 over others."""
        m = re.search(r"v(\d+)$", s["algorithm"])
        return (int(m.group(1)) if m else 0, s["type"] == "STAGES", s["updated"])

    def _distinct_sleeps(self) -> list[tuple[str, dict]]:
        """One session per sleep. Google re-analyses nights and keeps both
        versions, so overlapping sessions are the same sleep: keep the best."""
        ordered = sorted(self.sleeps.items(), key=lambda kv: kv[1]["start"])
        groups: list[list[tuple[str, dict]]] = []
        group_end = -1
        for item in ordered:
            if groups and item[1]["start"] < group_end:
                groups[-1].append(item)
                group_end = max(group_end, item[1]["end"])
            else:
                groups.append([item])
                group_end = item[1]["end"]
        chosen = []
        for group in groups:
            best = max(group, key=lambda kv: self._rank(kv[1]))
            if best[0] not in self.scores:  # borrow the night's score if only the other version has one
                for sid, _ in group:
                    if sid in self.scores:
                        self.scores[best[0]] = self.scores[sid]
                        break
            chosen.append(best)
        return chosen

    def _read_sleep_stages(self, rows) -> None:
        for row in rows:
            stage_id = row.get("sleep_stage_id")
            if stage_id in self._stage_ids:
                continue
            self._stage_ids.add(stage_id)
            kind = row.get("sleep_stage_type")
            if kind not in ("DEEP", "LIGHT", "REM", "AWAKE"):
                continue
            minutes = (_epoch(row["sleep_stage_end"]) - _epoch(row["sleep_stage_start"])) / 60
            if minutes > 0:
                self.stages[row["sleep_id"]][kind] += minutes

    def _read_sleep_scores(self, rows) -> None:
        for row in rows:
            score = _float(row.get("overall_score"))
            if row.get("sleep_id") and score is not None and score > 0:
                self.scores[row["sleep_id"]] = round(score, 1)

    # ------------------------------------------------------------ output

    def result(self) -> dict:
        hourly = []
        for key in sorted(self.hours):
            h = self.hours[key]
            if not (h.steps or h.distance or h.active_kcal or h.hr or h.spo2):
                continue
            hr = h.hr
            sp = h.spo2
            hourly.append([
                _hour_epoch(key),
                int(round(h.steps)),
                round(h.distance, 1),
                int(round(h.active_kcal)),
                round(sum(hr) / len(hr), 1) if hr else None,
                round(min(hr)) if hr else None,
                round(max(hr)) if hr else None,
                len(hr),
                round(sum(sp) / len(sp), 1) if sp else None,
                round(min(sp), 1) if sp else None,
                round(max(sp), 1) if sp else None,
                len(sp),
            ])

        sleep = []
        for sleep_id, s in self._distinct_sleeps():
            st = self.stages.get(sleep_id)
            staged = s["type"] == "STAGES" and st
            sleep.append([
                s["start"],
                s["end"],
                s["asleep"],
                round(st["DEEP"], 1) if staged else None,
                round(st["LIGHT"], 1) if staged else None,
                round(st["REM"], 1) if staged else None,
                round(st["AWAKE"], 1) if staged else s["awake"],
                self.scores.get(sleep_id),
            ])

        return {
            "format": FORMAT,
            "version": VERSION,
            "source": "fitbit",
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "hourly": {"columns": HOURLY_COLUMNS, "rows": hourly},
            "daily": {
                "columns": ["metric", "date", "value"],
                "rows": [[m, d, round(v, 2)] for (m, d), v in sorted(self.daily.items())],
            },
            "measurements": {
                "columns": ["metric", "ts", "value"],
                "rows": [list(m) for m in sorted(self.measurements, key=lambda m: m[1])],
            },
            "sleep": {"columns": SLEEP_COLUMNS, "rows": sleep},
        }


def convert(paths: list[str]) -> dict:
    c = Converter()
    for path in paths:
        c.add_zip(path)
    if not c.files_read:
        raise SystemExit("No Fitbit / Google Health data found in the Takeout.")
    return c.result()


def summary(history: dict) -> str:
    hourly = history["hourly"]["rows"]
    if not hourly:
        return "No hourly data."
    first = datetime.fromtimestamp(hourly[0][0], timezone.utc).date()
    last = datetime.fromtimestamp(hourly[-1][0], timezone.utc).date()
    per_year: dict[int, int] = defaultdict(int)
    for row in hourly:
        per_year[datetime.fromtimestamp(row[0], timezone.utc).year] += row[1]
    daily = defaultdict(int)
    for metric, _d, _v in history["daily"]["rows"]:
        daily[metric] += 1
    lines = [
        f"{first} to {last}: {len(hourly)} hours of activity",
        "Steps per year: " + ", ".join(f"{y} {s:,}" for y, s in sorted(per_year.items())),
        "Daily values: " + ", ".join(f"{m} {n}" for m, n in sorted(daily.items())),
        f"Sleeps: {len(history['sleep']['rows'])}, weights: {len(history['measurements']['rows'])}",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("takeout", nargs="+", help="Takeout zip file(s)")
    parser.add_argument("-o", "--output", default="fitbit-history.json.gz")
    args = parser.parse_args()
    history = convert(args.takeout)
    with gzip.open(args.output, "wt", encoding="utf-8") as f:
        json.dump(history, f, separators=(",", ":"))
    print(summary(history))
    print(f"Written {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
