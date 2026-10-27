"""The Fitbit / Google Health Takeout converter, on a synthetic Takeout."""

from __future__ import annotations

import gzip
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import fitbit_takeout  # noqa: E402

ROOT = "Takeout/Google Health/"
ACT = ROOT + "Physical Activity_GoogleData/"
FIT = ROOT + "Health Fitness Data_GoogleData/"


def _epoch(s: str) -> int:
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def _csv(header: str, *rows: str) -> str:
    return "\n".join((header, *rows)) + "\n"


def make_takeout(path: Path) -> Path:
    files = {
        # Tracker and phone both counted the same minute: only the tracker counts.
        ACT + "Steps/steps_2025-06-01.csv": _csv(
            "timestamp,steps,data source",
            "2025-06-01T00:10:00Z,40,Inspire 3",
            "2025-06-01T00:10:00Z,38,MobileTrack",
            "2025-06-01T00:11:00Z,60,Inspire 3",
            "2025-06-01T01:00:00Z,5,Inspire 3",
        ),
        ACT + "Distance/distance_2025-06-01.csv": _csv(
            "timestamp,distance,data source",
            "2025-06-01T00:10:00Z,30.5,Inspire 3",
            "2025-06-01T00:10:00Z,99.0,Fit Health Connect",
        ),
        # 5-second readings: minute means are 70 and 90.
        ACT + "Heart Rate/heart_rate_2025-06-01.csv": _csv(
            "timestamp,beats per minute,data source",
            "2025-06-01T00:10:00Z,68.0,Inspire 3",
            "2025-06-01T00:10:05Z,72.0,Inspire 3",
            "2025-06-01T00:11:00Z,90.0,Inspire 3",
            "2025-06-01T00:11:05Z,0.0,Inspire 3",
        ),
        ACT + "Oxygen Saturation/oxygen_saturation_2025-06-01.csv": _csv(
            "timestamp,oxygen saturation percentage,data source",
            "2025-06-01T00:10:00Z,96.0,Inspire 3",
            "2025-06-01T00:11:00Z,98.0,Inspire 3",
        ),
        ACT + "Active Energy Burned/active_energy_burned_2025-06-01.csv": _csv(
            "timestamp,Kilocalories,data source",
            "2025-06-01T00:10:00Z,3.4,Google Health App",
            "2025-06-01T00:11:00Z,4.0,Google Health App",
            "2025-06-01T00:11:30Z,5.0,Phone Health Connect",
        ),
        ACT + "Daily Resting Heart Rate/daily_resting_heart_rate.csv": _csv(
            "timestamp,beats per minute,data source",
            "2025-06-01T00:00:00Z,61.4,Google Health App",
            "2025-06-02T00:00:00Z,0.0,Google Health App",
        ),
        ACT + "Daily Heart Rate Variability/daily_heart_rate_variability.csv": _csv(
            "timestamp,average heart rate variability milliseconds,non rem heart rate beats per minute,"
            "entropy,deep sleep root mean square of successive differences milliseconds,data source",
            "2025-06-01T00:00:00Z,21.5,60,2.1,18,Google Health App",
        ),
        ACT + "Weight/weight.csv": _csv(
            "timestamp,weight grams,data source",
            "2025-06-01T21:00:00Z,90300,Google Health App",
        ),
        # The same night analysed twice (v1 and v2): keep v2 and its stages.
        FIT + "UserSleeps_2025-05-28.csv": _csv(
            "sleep_id,sleep_type,minutes_in_sleep_period,minutes_after_wake_up,minutes_to_fall_asleep,"
            "minutes_asleep,minutes_awake,minutes_longest_awakening,minutes_to_persistent_sleep,"
            "start_utc_offset,sleep_start,end_utc_offset,sleep_end,data_source,algorithm_version,"
            "sleep_created,sleep_last_updated",
            "100,STAGES,480,0,0,450,30,0,0,+10:00,2025-06-01T12:00:00Z,+10:00,2025-06-01T20:00:00Z,"
            "DERIVED,sleep_session_v1,x,2025-06-01T20:05:00Z",
            "200,STAGES,470,0,0,440,30,0,0,+10:00,2025-06-01T12:05:00Z,+10:00,2025-06-01T19:55:00Z,"
            "DERIVED,sleep_session_v2,x,2025-06-02T00:00:00Z",
            "300,CLASSIC,90,0,0,80,10,0,0,+10:00,2025-06-03T03:00:00Z,+10:00,2025-06-03T04:30:00Z,"
            "DERIVED,sleep_session_v1,x,y",
        ),
        FIT + "UserSleepStages_2025-05-28.csv": _csv(
            "sleep_id,sleep_stage_id,sleep_stage_type,start_utc_offset,sleep_stage_start,"
            "end_utc_offset,sleep_stage_end,data_source,algorithm_version,sleep_stage_created,"
            "sleep_stage_last_updated",
            "200,1,LIGHT,+10:00,2025-06-01T12:05:00Z,+10:00,2025-06-01T15:05:00Z,DERIVED,v,x,y",
            "200,2,DEEP,+10:00,2025-06-01T15:05:00Z,+10:00,2025-06-01T16:35:00Z,DERIVED,v,x,y",
            "200,3,REM,+10:00,2025-06-01T16:35:00Z,+10:00,2025-06-01T19:25:00Z,DERIVED,v,x,y",
            "200,4,AWAKE,+10:00,2025-06-01T19:25:00Z,+10:00,2025-06-01T19:55:00Z,DERIVED,v,x,y",
        ),
        # A later file repeats one stage: it must not be counted twice.
        FIT + "UserSleepStages_2025-06-28.csv": _csv(
            "sleep_id,sleep_stage_id,sleep_stage_type,start_utc_offset,sleep_stage_start,"
            "end_utc_offset,sleep_stage_end,data_source,algorithm_version,sleep_stage_created,"
            "sleep_stage_last_updated",
            "200,2,DEEP,+10:00,2025-06-01T15:05:00Z,+10:00,2025-06-01T16:35:00Z,DERIVED,v,x,y",
        ),
        FIT + "UserSleepScores_2025-05-28.csv": _csv(
            "sleep_id,sleep_score_id,data_source,score_utc_offset,score_time,overall_score,"
            "duration_score,composition_score,revitalization_score,sleep_time_minutes,"
            "deep_sleep_minutes,rem_sleep_percent,resting_heart_rate,sleep_goal_minutes,waso",
            "100,9,DERIVED,+10:00,2025-06-01T20:05:00Z,81.2,-1,-1,-1,450,90,20,60,480,5",
        ),
        # Things that must never be read.
        ACT + "Gps Location/gps_location_2025-06-01.csv": "timestamp,latitude\nx,-35.1\n",
        ROOT + "Health Fitness Data_GoogleData/UserConversations.csv": "secret\n",
    }
    with zipfile.ZipFile(path, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return path


def _rows(history: dict, section: str) -> list[dict]:
    cols = history[section]["columns"]
    return [dict(zip(cols, r)) for r in history[section]["rows"]]


def test_convert(tmp_path):
    history = fitbit_takeout.convert([str(make_takeout(tmp_path / "takeout.zip"))])
    assert history["format"] == "health_hub_history"

    hours = {r["hour_ts"]: r for r in _rows(history, "hourly")}
    h0 = hours[_epoch("2025-06-01T00:00:00Z")]
    assert h0["steps"] == 100  # phone's 38 ignored
    assert h0["distance_m"] == 30.5
    assert h0["active_calories"] == 7  # phone's 5 ignored
    assert (h0["hr_mean"], h0["hr_min"], h0["hr_max"], h0["hr_n"]) == (80.0, 70, 90, 2)
    assert (h0["spo2_mean"], h0["spo2_n"]) == (97.0, 2)
    assert hours[_epoch("2025-06-01T01:00:00Z")]["steps"] == 5

    daily = {(m, d): v for m, d, v in history["daily"]["rows"]}
    assert daily == {("resting_heart_rate", "2025-06-01"): 61.4, ("hrv", "2025-06-01"): 21.5}
    assert history["measurements"]["rows"] == [["weight", _epoch("2025-06-01T21:00:00Z"), 90.3]]

    sleeps = _rows(history, "sleep")
    assert len(sleeps) == 2  # v1 and v2 of the same night became one
    night, nap = sleeps
    assert night["start_ts"] == _epoch("2025-06-01T12:05:00Z")
    assert night["total_min"] == 440
    assert (night["deep_min"], night["light_min"], night["rem_min"], night["awake_min"]) == (
        90.0, 180.0, 170.0, 30.0,
    )
    assert night["score"] == 81.2  # borrowed from the v1 analysis of the same night
    assert nap["deep_min"] is None and nap["awake_min"] == 10


def test_cli_writes_gzip(tmp_path, monkeypatch, capsys):
    takeout = make_takeout(tmp_path / "takeout.zip")
    out = tmp_path / "history.json.gz"
    monkeypatch.setattr(sys, "argv", ["fitbit_takeout.py", str(takeout), "-o", str(out)])
    assert fitbit_takeout.main() == 0
    with gzip.open(out, "rt") as f:
        assert json.load(f)["source"] == "fitbit"
    assert "Sleeps: 2" in capsys.readouterr().out
