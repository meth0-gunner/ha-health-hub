#!/usr/bin/env python3
"""Health Hub Reviewer: runs Health Hub's daily review with Claude Code.

Health Hub (the integration) writes a request file; this add-on notices it,
runs Claude Code non-interactively with the prompt it contains, and writes the
answer back. Files live in the Home Assistant config folder:

    health_hub/review/request.json   written by Health Hub
    health_hub/review/response.json  written here
    health_hub/review/status.json    written here every poll (heartbeat)

Claude Code signs in with the login the Claude Code add-on keeps in
/homeassistant/.claudecode, so this uses the same Claude subscription.

Claude may only search and read the web. It cannot read files, run commands or
use any MCP server, so nothing beyond the request's summary can leave.

Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "0.1.0"
ROOT = Path(os.environ.get("HH_ROOT", "/homeassistant"))
DATA = Path(os.environ.get("HH_DATA", "/data"))
CLAUDE = os.environ.get("HH_CLAUDE_BIN", "claude")
LOGIN = ROOT / ".claudecode"
REVIEW_DIR = ROOT / "health_hub" / "review"
REQUEST = REVIEW_DIR / "request.json"
RESPONSE = REVIEW_DIR / "response.json"
STATUS = REVIEW_DIR / "status.json"
STATE = DATA / "state.json"
WORKDIR = Path(os.environ.get("HH_WORKDIR", "/tmp/health-hub-review"))
POLL_SECONDS = float(os.environ.get("HH_POLL_SECONDS", "15"))

# Claude gets the web tools and nothing else. --tools sets which tools exist at
# all; the deny list is a second lock. --restricted ignores the settings files
# the Claude Code add-on shares (its permissions and Home Assistant MCP server),
# and --safe-mode skips its CLAUDE.md, hooks, plugins and skills.
BLOCKED_TOOLS = "Bash,Edit,Write,Read,Glob,Grep,NotebookEdit,Task,TodoWrite,MultiEdit,LS"
WEB_TOOLS = "WebSearch,WebFetch"
MAX_RAW = 20000


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(message: str) -> None:
    print(f"[{now()}] {message}", flush=True)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_json(path: Path, data: Any) -> None:
    """Write atomically so Health Hub never reads half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def options() -> dict[str, Any]:
    opts = read_json(DATA / "options.json") or {}
    return {
        "model": (opts.get("model") or "").strip(),
        "web_research": opts.get("web_research", True) is not False,
        "max_turns": int(opts.get("max_turns") or 12),
        "timeout_minutes": int(opts.get("timeout_minutes") or 10),
    }


def link_login() -> None:
    """Point Claude Code at the Claude Code add-on's saved login."""
    if os.environ.get("HH_SKIP_LINKS"):
        return
    home = Path("/root")
    (home / ".config").mkdir(parents=True, exist_ok=True)
    (LOGIN / "config").mkdir(parents=True, exist_ok=True)
    links = {
        home / ".claude": LOGIN,
        home / ".config" / "claude-code": LOGIN / "config",
        home / ".claude.json": LOGIN / ".claude.json",
    }
    for link, target in links.items():
        if link.is_symlink():
            continue
        if link.is_dir():
            import shutil

            shutil.rmtree(link)
        elif link.exists():
            link.unlink()
        if target.name == ".claude.json" and not target.exists():
            target.touch()
        link.symlink_to(target)


def logged_in() -> bool:
    return (LOGIN / ".credentials.json").exists()


def claude_version() -> str:
    try:
        return Path("/etc/claude-code-version").read_text().strip()
    except OSError:
        return "unknown"


def extract_json(text: str) -> Any:
    """Pull the JSON object out of Claude's answer (fenced or bare)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object in the answer")
        candidate = text[start : end + 1]
    return json.loads(candidate)


def parse_envelope(stdout: str) -> dict[str, Any] | None:
    """Claude Code's JSON output: one result object (or, verbosely, a list)."""
    try:
        data = json.loads(stdout)
    except ValueError:
        return None
    if isinstance(data, list):
        results = [m for m in data if isinstance(m, dict) and m.get("type") == "result"]
        data = results[-1] if results else None
    return data if isinstance(data, dict) else None


def build_command(opts: dict[str, Any]) -> list[str]:
    cmd = [
        CLAUDE,
        "-p",
        "--output-format", "json",
        "--max-turns", str(opts["max_turns"]),
        "--restricted",
        "--safe-mode",
        "--strict-mcp-config",
    ]
    # These options take a list, so each is passed as one "--name=value" word
    # (a bare value after them would be read as more tool names).
    if opts["web_research"]:
        cmd += [f"--tools={WEB_TOOLS}", f"--allowedTools={WEB_TOOLS}", f"--disallowedTools={BLOCKED_TOOLS}"]
    else:
        cmd += ["--tools=", f"--disallowedTools={BLOCKED_TOOLS},{WEB_TOOLS}"]
    if opts["model"]:
        cmd += ["--model", opts["model"]]
    return cmd


def run_review(request: dict[str, Any], opts: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    response: dict[str, Any] = {
        "id": request.get("id"),
        "status": "error",
        "started": now(),
        "reviewer_version": VERSION,
        "claude_code_version": claude_version(),
        "review": None,
        "error": None,
    }
    prompt = request.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        response["error"] = "The request had no prompt."
        return response
    WORKDIR.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            build_command(opts),
            input=prompt,
            capture_output=True,
            text=True,
            cwd=WORKDIR,
            timeout=opts["timeout_minutes"] * 60,
            env={**os.environ, "HOME": os.environ.get("HH_HOME", "/root")},
        )
    except subprocess.TimeoutExpired:
        response["error"] = f"Claude took longer than {opts['timeout_minutes']} minutes."
        return response
    except OSError as err:
        response["error"] = f"Could not start Claude Code: {err}"
        return response

    response["duration_ms"] = int((time.monotonic() - started) * 1000)
    envelope = parse_envelope(proc.stdout)
    if envelope is None:
        tail = (proc.stderr or proc.stdout or "").strip()[-500:]
        response["error"] = f"Claude Code exited with code {proc.returncode}: {tail}"
        return response

    text = envelope.get("result") or ""
    response["raw"] = text[:MAX_RAW]
    response["cost_usd"] = envelope.get("total_cost_usd")
    response["num_turns"] = envelope.get("num_turns")
    if envelope.get("is_error") or envelope.get("subtype") not in (None, "success"):
        response["error"] = f"Claude reported a problem: {envelope.get('subtype') or text[:300]}"
        return response
    try:
        response["review"] = extract_json(text)
    except ValueError as err:
        response["error"] = f"The answer wasn't in the expected format ({err})."
        return response
    response["status"] = "ok"
    return response


def heartbeat(state: str, detail: str | None = None) -> None:
    write_json(
        STATUS,
        {
            "alive": now(),
            "state": state,
            "detail": detail,
            "logged_in": logged_in(),
            "reviewer_version": VERSION,
            "claude_code_version": claude_version(),
        },
    )


def poll_once(memory: dict[str, Any]) -> None:
    if not logged_in():
        heartbeat("no_login", "Sign in to Claude in the Claude Code add-on first.")
        return
    request = read_json(REQUEST)
    if not isinstance(request, dict) or not request.get("id"):
        heartbeat("idle")
        return
    if request["id"] == memory.get("last_id"):
        heartbeat("idle")
        return
    log(f"Running review {request['id']}")
    heartbeat("running", str(request["id"]))
    response = run_review(request, options())
    response["finished"] = now()
    write_json(RESPONSE, response)
    memory["last_id"] = request["id"]
    write_json(STATE, memory)
    log(f"Review {request['id']}: {response['status']}" + (f" ({response['error']})" if response["error"] else ""))
    heartbeat("idle" if response["status"] == "ok" else "error", response.get("error"))


def main() -> int:
    log(f"Health Hub Reviewer {VERSION}, Claude Code {claude_version()}")
    link_login()
    memory = read_json(STATE) or {}
    if not logged_in():
        log("No Claude login found in /homeassistant/.claudecode; waiting for one.")
    while True:
        try:
            poll_once(memory)
        except Exception as err:  # keep running; report on the next heartbeat
            log(f"Unexpected error: {err!r}")
            try:
                heartbeat("error", repr(err)[:300])
            except OSError:
                pass
        if os.environ.get("HH_ONCE"):
            return 0
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
