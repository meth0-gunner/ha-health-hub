# Gadgetbridge data for the Xiaomi Smart Band 8 Pro

Mapped from a real export on 26 October 2026: Gadgetbridge database version 151,
band model M2333B1, firmware 2.2.31. The band was not yet worn, so the shape is
confirmed but some value meanings still need real readings (marked *to confirm*).

## Tables used

| Table | Timestamp | One row per | Used for |
|---|---|---|---|
| `XIAOMI_ACTIVITY_SAMPLE` | seconds | minute | steps, distance (cm), active calories, heart rate, stress, SpO2 |
| `XIAOMI_DAILY_SUMMARY_SAMPLE` | milliseconds, local midnight | day (rewritten during the day) | resting HR, HR min/max/avg, stress and SpO2 summaries, standing, calories, vitality, training load |
| `XIAOMI_SLEEP_TIME_SAMPLE` | milliseconds (*to confirm*) | sleep session | bed and wake times, minutes per stage |
| `XIAOMI_SLEEP_STAGE_SAMPLE` | milliseconds (*to confirm*) | stage change | sleep stage timeline (stage codes *to confirm*) |
| `XIAOMI_MANUAL_SAMPLE` | milliseconds (*to confirm*) | spot check | measurements taken on the band (type codes *to confirm*) |
| `BATTERY_LEVEL` | **seconds** | reading | band battery |
| `BASE_ACTIVITY_SUMMARY` | milliseconds (`START_TIME`) | workout | workout type, times, summary JSON (partial support in Gadgetbridge) |
| `DEVICE` | — | device | names devices (Bluetooth address not sent) |

Timestamps are converted by size as well as by the declared unit, so a wrong
guess about seconds versus milliseconds cannot corrupt times.

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
