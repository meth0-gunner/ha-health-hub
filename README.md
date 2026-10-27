# Health Hub

A cloud-free replacement for the Fitbit app: band data from
[Gadgetbridge](https://gadgetbridge.org) logged, charted and used in Home Assistant.

Built for a Xiaomi Smart Band 8 Pro on a Pixel, with Home Assistant on an HA Green.

## How it works

```
Band ──BLE──> Gadgetbridge ──hourly export──> Health Hub app ──HTTPS──> Health Hub integration
             (phone)          (SQLite file)    (phone, this repo)        (Home Assistant, this repo)
```

1. Gadgetbridge syncs the band and exports its database every hour.
2. The phone app asks Home Assistant what it needs (a *sync plan*), reads only
   those rows from the export, and posts them in batches.
3. The integration stores them, writes long-term statistics on the times the
   data actually happened, and updates sensors.

Home Assistant owns the sync cursor, so a restored backup simply asks the phone
to re-send what is missing. Each sync re-reads the last 48 hours, because
Gadgetbridge updates some rows after the fact (today's daily summary, for
example).

## What's in Home Assistant

**Sensors** (device "Health Hub"): steps, distance, active calories and stress
today; latest heart rate, blood oxygen and stress; resting heart rate; vitality
score; last sleep (with stage breakdown); band battery; last sync; last reading.

**Long-term statistics** (for statistics graph cards, kept for good):

| Statistic | Type |
|---|---|
| `health_hub:steps`, `health_hub:distance`, `health_hub:active_calories` | hourly totals |
| `health_hub:heart_rate`, `health_hub:stress`, `health_hub:spo2` | hourly mean, min, max |
| `health_hub:resting_heart_rate`, `health_hub:vitality_score` | one value per day |
| `health_hub:sleep_duration`, `deep_sleep`, `light_sleep`, `rem_sleep`, `awake_in_bed` | hours per night, credited to the wake-up day |

**Minute-level detail** for the last 90 days (configurable), for intraday charts,
through the websocket command `health_hub/samples`.

**Service** `health_hub.rebuild_statistics` rewrites every statistic from stored data.

## Privacy

Only the columns listed in
[`core/gadgetbridge.py`](custom_components/health_hub/core/gadgetbridge.py) ever
leave the phone. Names, birthdays, Bluetooth addresses, workout locations and
GPS tracks stay on the phone. Gadgetbridge exports and `*.db` files are excluded
from this repository by `.gitignore`.

The endpoints need an **admin** user's access token.

## Repository layout

| Path | What |
|---|---|
| `custom_components/health_hub/` | Home Assistant integration |
| `custom_components/health_hub/core/` | Logic with no Home Assistant dependency: table map, store, statistics, sync protocol |
| `tools/sync_export.py` | Sends an export from a PC; same logic as the phone app (standard library only) |
| `tests/` | Tests, including a full Home Assistant instance receiving a synthetic export |
| `docs/` | Notes on Gadgetbridge's data |
| `android/` | Phone app (coming next) |

## Status

- [x] Integration: sync endpoints, store, statistics, sensors, dashboard data command
- [ ] Phone app
- [ ] Fitbit history import
- [ ] Dashboards, goals and streaks
- [ ] Automations: morning summary, alerts
- [ ] Presence via the band

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```
