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

**Actions** `health_hub.rebuild_statistics` rewrites every statistic from stored
data; `health_hub.request_review` asks for a fresh daily review.

## Health page

A **Health** item in the sidebar (admins only) is Health Hub's own page, built
into the integration with hand-drawn charts and no add-on cards:

- **Overview**: readiness, day load and energy; the daily review; goals with
  streaks; one-tap gym (Push, Pull, Legs) and Compex logging with 4-week blocks
  and rewards; highlights; today at a glance; last night.
- **Sleep**, **Readiness**, **Activity & load**, **Heart**, **Stress & energy**,
  **Body** (weigh-ins and goal), **Training** (calendar, past blocks, rewards
  history) and **Settings** (goals and targets).
- Day, Week, Month, Year or a custom range, and ‹ › to step through them.

Every score and statement is worked out from your own data with a stated rule;
"Why?" shows the rule, your numbers and, for published thresholds, the source.

Readiness, sleep score, day load and energy are Health Hub's own calculations
(`core/metrics.py`); the band's readings are estimates, not medical
measurements.

## Daily review

Each morning, once last night's sleep has synced, Health Hub asks Claude for a
short review of your figures, checked against current research with web search.
It runs on your existing Claude subscription through the **Health Hub Reviewer**
add-on in this repository, which reuses the login of the Claude Code add-on.

1. Settings → Add-ons → Add-on store → ⋮ → Repositories, add
   `https://github.com/meth0-gunner/ha-health-hub`.
2. Install **Health Hub Reviewer** and start it. It needs the Claude Code add-on
   installed and signed in.

Only a summary of figures is sent (nightly and daily totals, averages and
baselines); never minute readings, names or device details. The add-on lets
Claude search and read the web and nothing else: no files, commands or Home
Assistant tools. Every request and answer is kept, with the summary that was sent.

- **Sensors**: Daily review (headline; the full review is on the Health page)
  and Reviewer (whether the add-on is there and signed in).
- **Action** `health_hub.request_review` (Review now).
- **Options**: turn the review off, or change the time it's written anyway if
  no night has synced (10:00 by default).
- Websocket command `health_hub/review`.

If no review appears, look at the Reviewer sensor and the add-on's log.

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
| `health_hub_reviewer/` | Home Assistant add-on that writes the daily review with Claude Code |
| `repository.yaml` | Makes this repository an add-on repository too |

## Status

- [x] Integration: sync endpoints, store, statistics, sensors, dashboard data command
- [x] Phone app: export folder, hourly background sync, sync now, status
- [x] Fitbit history import
- [x] Daily review with Claude (Reviewer add-on)
- [x] Health page: scores, goals and streaks, training and rewards, weight
- [ ] Automations: morning summary, alerts
- [ ] Presence via the band

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```
