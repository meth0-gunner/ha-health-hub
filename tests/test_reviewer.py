"""Tests for the Health Hub Reviewer add-on, using a stand-in for Claude Code."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REVIEWER = Path(__file__).parents[1] / "health_hub_reviewer" / "reviewer.py"

FAKE_CLAUDE = r'''#!{python}
import json, os, sys
open(os.environ["FAKE_ARGS"], "w").write(json.dumps(sys.argv[1:]))
open(os.environ["FAKE_PROMPT"], "w").write(sys.stdin.read())
mode = os.environ.get("FAKE_MODE", "ok")
if mode == "crash":
    print("something went wrong", file=sys.stderr)
    sys.exit(3)
answer = {
    "ok": 'Here you go:\n```json\n{"headline": "Good night", "items": []}\n```',
    "bare": 'Sure. {"headline": "Bare"} Done.',
    "prose": "Sorry, no JSON here",
}[mode]
result = {"type": "result", "subtype": "success", "is_error": False,
          "result": answer, "total_cost_usd": 0.12, "num_turns": 4}
print(json.dumps([{"type": "system"}, result] if mode == "bare" else result))
'''


@pytest.fixture
def addon(tmp_path):
    root, data, bin_dir = tmp_path / "ha", tmp_path / "data", tmp_path / "bin"
    (root / ".claudecode").mkdir(parents=True)
    (root / ".claudecode" / ".credentials.json").write_text("{}")
    data.mkdir()
    bin_dir.mkdir()
    fake = bin_dir / "claude"
    fake.write_text(FAKE_CLAUDE.replace("{python}", sys.executable))
    fake.chmod(0o755)
    review = root / "health_hub" / "review"

    def request(rid, prompt="Review please"):
        review.mkdir(parents=True, exist_ok=True)
        (review / "request.json").write_text(json.dumps({"id": rid, "prompt": prompt}))

    def run(mode="ok", options=None):
        if options is not None:
            (data / "options.json").write_text(json.dumps(options))
        args = tmp_path / "args.json"
        args.unlink(missing_ok=True)
        env = {
            **os.environ,
            "HH_ROOT": str(root), "HH_DATA": str(data), "HH_CLAUDE_BIN": str(fake),
            "HH_SKIP_LINKS": "1", "HH_ONCE": "1", "HH_WORKDIR": str(tmp_path / "work"),
            "FAKE_ARGS": str(args), "FAKE_PROMPT": str(tmp_path / "prompt.txt"),
            "FAKE_MODE": mode,
        }
        subprocess.run([sys.executable, str(REVIEWER)], env=env, check=True, timeout=60)
        response = review / "response.json"
        return {
            "args": json.loads(args.read_text()) if args.exists() else None,
            "response": json.loads(response.read_text()) if response.exists() else None,
            "status": json.loads((review / "status.json").read_text()),
            "prompt": (tmp_path / "prompt.txt").read_text() if args.exists() else None,
        }

    return request, run, root


def test_review_runs_with_web_tools_only(addon):
    request, run, _ = addon
    request("r1")
    out = run()
    assert out["prompt"] == "Review please"
    args = out["args"]
    assert "--tools=WebSearch,WebFetch" in args
    assert "--allowedTools=WebSearch,WebFetch" in args
    blocked = next(a for a in args if a.startswith("--disallowedTools=")).split("=", 1)[1].split(",")
    assert {"Bash", "Read", "Write", "Edit", "Glob", "Grep"} <= set(blocked)
    assert {"--restricted", "--safe-mode", "--strict-mcp-config"} <= set(args)
    assert "--model" not in args
    resp = out["response"]
    assert resp["id"] == "r1" and resp["status"] == "ok"
    assert resp["review"] == {"headline": "Good night", "items": []}
    assert resp["cost_usd"] == 0.12
    assert out["status"]["state"] == "idle" and out["status"]["logged_in"]


def test_same_request_runs_once(addon):
    request, run, _ = addon
    request("r1")
    run()
    assert run()["args"] is None


def test_options_without_web_and_with_model(addon):
    request, run, _ = addon
    request("r2")
    args = run(options={"web_research": False, "model": "sonnet", "max_turns": 5})["args"]
    assert "--tools=" in args
    assert not any(a.startswith("--allowedTools") for a in args)
    assert "WebSearch" in next(a for a in args if a.startswith("--disallowedTools="))
    assert args[args.index("--model") + 1] == "sonnet"
    assert args[args.index("--max-turns") + 1] == "5"


def test_bare_json_in_verbose_output(addon):
    request, run, _ = addon
    request("r3")
    assert run("bare")["response"]["review"] == {"headline": "Bare"}


@pytest.mark.parametrize(("mode", "needle"), [("crash", "code 3"), ("prose", "expected format")])
def test_failures_are_reported(addon, mode, needle):
    request, run, _ = addon
    request("r4")
    out = run(mode)
    assert out["response"]["status"] == "error"
    assert needle in out["response"]["error"]
    assert out["status"]["state"] == "error"


def test_waits_for_login(addon):
    request, run, root = addon
    (root / ".claudecode" / ".credentials.json").unlink()
    request("r5")
    out = run()
    assert out["args"] is None and out["response"] is None
    assert out["status"]["state"] == "no_login"
