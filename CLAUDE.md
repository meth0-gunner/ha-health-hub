# Health Hub — notes for Claude

Cloud-free Fitbit-app replacement: Gadgetbridge (Xiaomi Smart Band 8 Pro, Pixel)
→ our phone app → our Home Assistant integration. Owner: Nick (not a developer;
explain in plain terms, he installs things, Claude writes and pushes code).

## Rules

- Never commit Gadgetbridge exports, `*.db` files or anything with personal data.
  Test data is synthetic (`tests/gbfixture.py`) using the schema-only fixture.
- `custom_components/health_hub/core/` must not import Home Assistant.
- Gadgetbridge table/column knowledge lives only in `core/gadgetbridge.py`; the
  phone app stays generic and reads whatever the sync plan asks for.
- Only send columns that are needed; never names, birthdays, MACs, locations, GPX.
- Sensors have no state class on purpose; long-term history is external
  statistics (`health_hub:*`) written on the true times.
- Run `pytest -q` before pushing (HA test harness: `pytest-homeassistant-custom-component`).
- Target current Home Assistant (statistics metadata uses `mean_type` and
  `unit_class`; `has_mean` is gone).

## Decisions so far

- Freshness: hourly. No Tasker, no Health Connect, no third-party apps.
- Minute-level detail kept 90 days; hourly/daily kept for good.
- Weight is manual entry in HA. Dashboards in HA only, admin-only.
- Requirements doc: https://claude.ai/artifact/QiGGRNb8ibizPfAm9qp3o2
