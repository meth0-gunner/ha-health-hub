"""Preview the Health page in a browser without Home Assistant.

Serves the panel's files and answers its websocket calls from a Health Hub
store file, using the same core code as the integration:

    python3 tools/panel_preview.py path/to/health_hub.db --tz Australia/Sydney
    # then open http://localhost:8765/health/

For development only. Changes it makes (logging training, weights, settings)
go into the store file given, so use a copy.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custom_components.health_hub.core import settings as settings_mod  # noqa: E402
from custom_components.health_hub.core import training, views  # noqa: E402
from custom_components.health_hub.core.metrics import Calculator  # noqa: E402
from custom_components.health_hub.core.store import Store  # noqa: E402

FRONTEND = ROOT / "custom_components" / "health_hub" / "frontend"

PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Health preview</title><style>body{margin:0;background:#0F1218}</style></head><body>
<health-hub-panel></health-hub-panel>
<script type="module">
import "/static/panel.js";
const el = document.querySelector("health-hub-panel");
const call = async (msg) => {
  const r = await fetch("/ws", {method: "POST", body: JSON.stringify(msg)});
  const body = await r.json();
  if (!r.ok) throw body;
  return body;
};
el.route = {prefix: "/health", path: location.pathname.slice(7) || "/"};
el.hass = {callWS: call, callService: (d, s, data) => call({type: "service", domain: d, service: s, data})};
</script></body></html>"""


class App:
    def __init__(self, db: str, tz: str, today: str | None, review: str | None) -> None:
        self.store = Store(db)
        self.tz = ZoneInfo(tz)
        self.calc = Calculator(self.store, self.tz)
        self.fixed_today = date.fromisoformat(today) if today else None
        self.review = json.loads(Path(review).read_text()) if review else None

    def today(self) -> date:
        return self.fixed_today or datetime.now(self.tz).date()

    def handle(self, msg: dict) -> object:
        t = msg["type"]
        s = settings_mod.load(self.store)
        today = self.today()
        d = lambda k: date.fromisoformat(msg[k]) if msg.get(k) else today  # noqa: E731
        if t == "health_hub/info":
            return {
                "version": "preview", "time_zone": str(self.tz), "today": today.isoformat(),
                "first_date": None, "last_sync": datetime.now().astimezone().isoformat(), "last_reading": None,
                "settings": views.settings_view(s), "sources": views.sources_view(),
            }
        if t == "health_hub/day":
            now = int(time.time()) if not self.fixed_today else int(datetime.combine(today, datetime.min.time(), self.tz).timestamp()) + 17 * 3600
            return views.day_view(self.calc, self.store, s, d("date"), today, now)
        if t == "health_hub/range":
            return views.range_view(self.calc, s, d("start"), d("end"))
        if t == "health_hub/night":
            return views.night_view(self.calc, s, d("date"))
        if t == "health_hub/sleep_history":
            return views.long_term_sleep(self.calc, s, today)
        if t == "health_hub/settings/set":
            return views.settings_view(settings_mod.update(self.store, msg["changes"]))
        if t == "health_hub/training":
            return training.state(self.store, s, today, d("date"))
        if t == "health_hub/training/log":
            training.log(self.store, d("date"), msg["kind"], msg.get("variant"))
            return training.state(self.store, s, today, d("date"))
        if t == "health_hub/training/undo":
            self.store.remove_training(msg["log_id"])
            return training.state(self.store, s, today, d("date"))
        if t == "health_hub/rewards/spend":
            training.spend(self.store)
            return training.state(self.store, s, today, d("date"))
        if t == "health_hub/weight/log":
            self.store.add_measurement(int(time.time()), "weight", float(msg["kg"]), "manual")
            return views.weight_view(self.store, s, self.tz)
        if t == "health_hub/weight/delete":
            self.store.delete_measurement(int(msg["ts"]), "weight", "manual")
            return views.weight_view(self.store, s, self.tz)
        if t == "health_hub/review":
            return self.review or {"enabled": True, "reviewer": {"state": "not_installed"}, "latest": None, "last_attempt": None}
        if t == "service":
            return {}
        raise ValueError(f"unknown command {t}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("db")
    p.add_argument("--tz", default="Australia/Sydney")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--today", help="pretend today is this date (YYYY-MM-DD)")
    p.add_argument("--review", help="JSON file answering health_hub/review")
    args = p.parse_args()
    app = App(args.db, args.tz, args.today, args.review)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path.startswith("/static/"):
                f = (FRONTEND / path[len("/static/"):]).resolve()
                if FRONTEND in f.parents and f.is_file():
                    return self._send(200, f.read_bytes(), "text/javascript")
                return self._send(404, b"not found", "text/plain")
            return self._send(200, PAGE.encode(), "text/html")

        def do_POST(self):
            msg = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            try:
                result = app.handle(msg)
                self._send(200, json.dumps(result).encode(), "application/json")
            except Exception as err:  # noqa: BLE001
                self._send(400, json.dumps({"code": "error", "message": str(err)}).encode(), "application/json")

    print(f"http://localhost:{args.port}/health/")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
