# Gadgetbridge data for the Xiaomi Smart Band 8 Pro

Mapped from a real export on 26 October 2026: Gadgetbridge database version 151,
band model M2333B1, firmware 2.2.31. The band was not yet worn, so the shape is
confirmed but some value meanings still need real readings (marked *to confirm*).

## Tables used

| Table | Timestamp | One row per | Used for |
|---|---|---|---|
| `XIAOMI_ACTIVITY_SAMPLE` | seconds | minute | steps, distance (cm), active calories, heart rate, stress, SpO2 |
| `XIAOMI_DAILY_SUMMARY_SAMPLE` | milliseconds, local midnight | day (rewritten during the day) | resting HR, HR min/max/avg, stress and SpO2 summaries, standing, calories, vitality, training load |
| `XIAOMI_SLEEP_TIME_SAMPLE` | milliseconds | sleep session | bed and wake times; total, deep, light, REM and awake minutes (total excludes awake) |
| `XIAOMI_SLEEP_STAGE_SAMPLE` | milliseconds | stage change | sleep stage timeline: 2 deep, 3 light, 4 REM, 5 awake |
| `XIAOMI_MANUAL_SAMPLE` | milliseconds (*to confirm*) | spot check | measurements taken on the band (type codes *to confirm*) |
| `BATTERY_LEVEL` | **seconds** | reading | band battery |
| `BASE_ACTIVITY_SUMMARY` | milliseconds (`START_TIME`) | workout | workout type, times, summary JSON (partial support in Gadgetbridge) |
| `DEVICE` | — | device | names devices (Bluetooth address not sent) |

Timestamps are converted by size as well as by the declared unit, so a wrong
guess about seconds versus milliseconds cannot corrupt times.

## Confirmed with a night's real data (27 October 2026)

- Sleep stage codes: 2 deep, 3 light, 4 REM, 5 awake (each stage's minutes in
  the timeline matched the session totals within a few minutes).
- `STANDING` in the daily summary is a bitmask, one bit per hour of the day in
  which you stood; Health Hub stores the number of hours.
- `CALORIES` and `ACTIVE_CALORIES` in the daily summary are the same value
  (active calories only, no resting metabolism), and match the minute samples.
- Daily step totals match the sum of the minute samples.
- Heart rate is sampled at the band's configured interval (about every other
  minute by day, every minute overnight by default); stress and SpO2 less often.

## Conventions

- **No reading** is stored as 0 (sometimes 255 or -1). Health Hub keeps a value
  only inside a plausible range: heart rate 25–240, stress 1–100, SpO2 70–100.
- **Time zone** in the daily summary is in 15-minute steps: 44 means UTC+11:00.
- `ENERGY` in activity samples is -1 for this band and is not used.

## Not available for this band

- **HRV**: no Xiaomi table.
- **Floors**: no field.
- **VO2 max**: listed by Gadgetbridge as not yet supported for Xiaomi bands.

## If Gadgetbridge changes

Gadgetbridge's database is internal and can change between versions. Table and
column names live in one place,
[`custom_components/health_hub/core/gadgetbridge.py`](../custom_components/health_hub/core/gadgetbridge.py).
Missing columns are skipped rather than failing, and the *Last band reading*
sensor shows when data stops arriving.
