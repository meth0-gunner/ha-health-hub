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
- Phone app (`android/`) is built only by GitHub Actions (this workspace can't
  reach Google's Maven). Published APKs are signed with `android/signing/release.p12`
  (encrypted; password is the `HH_KEYSTORE_PASSWORD` repo secret). Never replace
  that key casually: a new key forces Nick to uninstall and reinstall.
- To release, bump `version` in `custom_components/health_hub/manifest.json` on main;
  release.yml tests, builds the signed APK and publishes `vX.Y.Z` (tags can't be
  pushed from Claude sessions). HACS installs from those releases.
- Run `pytest -q` before pushing (HA test harness: `pytest-homeassistant-custom-component`).
- The daily review goes through the Health Hub Reviewer add-on
  (`health_hub_reviewer/`), which runs `claude -p` on the Claude Code add-on's
  login (`/homeassistant/.claudecode`). Exchange is files in
  `/config/health_hub/review/` (request, response, status). Claude gets only
  WebSearch/WebFetch (`--tools`, `--restricted`, `--safe-mode`,
  `--strict-mcp-config`). Only `core/review.py`'s summary of figures is sent.
  Bump the add-on's `version` in its config.yaml when it changes, or HA won't
  offer the update. `addon.yml` test-builds it for amd64 and aarch64.
- Health page: `frontend/` (plain ES modules, no build step, no libraries,
  hand-drawn SVG) served at `/health_hub_static/<version>/`, registered as an
  admin-only panel. Its data comes from `panel_api.py` commands built on
  `core/metrics.py` (scores), `core/views.py` (page payloads), `core/training.py`
  (blocks and rewards), `core/settings.py` and `core/sources.py` (cited sources;
  add one only after opening it). Preview without HA:
  `python3 tools/panel_preview.py <copy of health_hub.db>` and take screenshots
  with Playwright before releasing.
- Target current Home Assistant (statistics metadata uses `mean_type` and
  `unit_class`; `has_mean` is gone).

## Decisions so far

- Freshness: hourly. No Tasker, no Health Connect, no third-party apps.
- Minute-level detail kept 90 days; hourly/daily kept for good.
- Weight is manual entry in HA. Dashboards in HA only, admin-only.
- Requirements doc: https://claude.ai/artifact/QiGGRNb8ibizPfAm9qp3o2
