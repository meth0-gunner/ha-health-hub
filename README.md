# Health Hub

A cloud-free replacement for the Fitbit app: band data from
[Gadgetbridge](https://gadgetbridge.org) logged, charted and used in Home Assistant.

Built for a Xiaomi Smart Band 8 Pro on a Pixel, with Home Assistant on an HA Green.

## Install

**Home Assistant**

1. HACS → three-dot menu → **Custom repositories** → add
   `https://github.com/meth0-gunner/ha-health-hub`, type **Integration**.
2. Find **Health Hub** in HACS, **Download**, then restart Home Assistant.
3. **Settings → Devices & services → Add integration → Health Hub**.
4. Your profile → **Security** → **Long-lived access tokens** → create one called
   "Health Hub phone" (the user must be an admin). Copy it.

**Phone**

1. Gadgetbridge: Settings → Automations → **Auto export database**, hourly, into a
   folder such as Documents/Gadgetbridge.
2. Download the latest `HealthHub-x.y.z.apk` from
   [Releases](https://github.com/meth0-gunner/ha-health-hub/releases) on the phone
   and open it to install.
3. In the app: enter your Home Assistant address (your Nabu Casa address works at
   home and away) and the token, tap **Save and test**, choose the export folder,
   allow background running, then **Sync now**.

## Importing Fitbit history

1. Download your data with Google Takeout (Fitbit / Google Health).
2. Convert it on any computer with Python 3.11+:
   `python3 tools/fitbit_takeout.py takeout-*.zip -o fitbit-history.json.gz`
3. Home Assistant: Health Hub → **Configure** → **Import history** → upload the file.

Steps, distance and heart rate use the tracker's own readings (phone sources are
skipped, as the Fitbit app does). Nights Google re-analysed are counted once. The
band's own data wins on any day both recorded, and importing again replaces the
earlier import.

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
| `health_hub:resting_heart_rate`, `hrv`, `respiratory_rate`, `weight`, `vitality_score` | one value per day |
| `health_hub:sleep_duration`, `deep_sleep`, `light_sleep`, `rem_sleep`, `awake_in_bed`, `sleep_score` | per night, credited to the wake-up day |

HRV, breathing rate and sleep score come from imported Fitbit history (the band
doesn't measure them in Gadgetbridge).

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
| `tools/fitbit_takeout.py` | Converts a Google Takeout of Fitbit data into a history file to import |
| `tests/` | Tests, including a full Home Assistant instance receiving a synthetic export |
| `docs/` | Notes on Gadgetbridge's data |
| `android/` | Phone app (built by GitHub Actions; signed APKs appear under Releases) |

## Status

- [x] Integration: sync endpoints, store, statistics, sensors, dashboard data command
- [x] Phone app: export folder, hourly background sync, sync now, status
- [x] Fitbit history import
- [ ] Dashboards, goals and streaks
- [ ] Automations: morning summary, alerts
- [ ] Presence via the band

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```
