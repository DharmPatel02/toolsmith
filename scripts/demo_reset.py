"""P4.3.1: put the demo back to the same starting screen.

Steps (each reported; a missing optional input is skipped with a reason, never faked):
  1. init_db            idempotent collections / indexes / action_vocab seed        (P1 script)
  2. seed history       POST data/seed/history.jsonl via the API, --reset           (P1 script)
  3. screen frames      replay the 3 UC1 recordings -> /capture/batch, backdated     (P2 script)
  4. cached generations warm the LLM cache: forge UC1, heal UC3, frame labels     (P2 script)
  5. mock site v1       POST /demo/mocksite/v1
  6. freeze vocab       VOCAB_FROZEN=1 in .env (the interpreter reads it; restart api/worker)
  7. snapshot           /tools, /suggestions, /suggestions/declined, /policy, compared with
                        the last run: "running it twice gives the same starting screen"

    python scripts/demo_reset.py [--api http://localhost:8000] [--skip precompute,frames]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / ".cache" / "demo_reset_snapshot.json"
RECORDINGS = ROOT / "data" / "recordings" / "uc1"
STEPS = ("init_db", "seed", "frames", "precompute", "mocksite", "freeze", "snapshot")


def http(api: str, method: str, path: str) -> dict | list:
    req = urllib.request.Request(api + path, data=b"" if method == "POST" else None, method=method)
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read())


def run(cmd: list[str]) -> tuple[bool, str]:
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT / "backend"), str(ROOT)])}
    proc = subprocess.run(
        [sys.executable, *cmd], cwd=ROOT, capture_output=True, text=True, env=env, check=False
    )
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
    return proc.returncode == 0, " | ".join(tail)


def set_env_flag(key: str, value: str) -> str:
    env = ROOT / ".env"
    if not env.exists():
        return "no .env (set VOCAB_FROZEN=1 in the api/worker environment)"
    lines = env.read_text(encoding="utf-8").splitlines()
    out = [line for line in lines if not line.startswith(f"{key}=")] + [f"{key}={value}"]
    env.write_text("\n".join(out) + "\n", encoding="utf-8")
    return f"{key}={value} written to .env; restart api + worker to apply"


def snapshot(api: str) -> dict:
    """What the demo's first screens show. Routes that aren't live yet are recorded, not fatal."""
    state, missing = {}, []
    for key, path in (
        ("tools", "/tools"),
        ("suggestions", "/suggestions"),
        ("declined", "/suggestions/declined"),
        ("policy", "/policy"),
    ):
        try:
            state[key] = http(api, "GET", path)
        except urllib.error.HTTPError as exc:
            missing.append(f"{path} {exc.code}")
            state[key] = None
    return {
        "tools": sorted((t["name"], t["trust"], t["status"]) for t in state["tools"] or []),
        "suggestions": sorted(s["title"] for s in state["suggestions"] or []),
        "declined": sorted(s["title"] for s in state["declined"] or []),
        "policy": state["policy"]
        and {"thresholds": state["policy"]["thresholds"], "rules": len(state["policy"]["rules"])},
        "missing": missing,
    }


def main(args: argparse.Namespace) -> int:
    api = args.api.rstrip("/")
    skip = set(filter(None, args.skip.split(",")))
    results: list[tuple[str, str, str]] = []

    def step(name: str, fn) -> None:
        if name in skip:
            results.append((name, "SKIP", "--skip"))
            return
        try:
            status, detail = fn()
        except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
            status, detail = "FAIL", str(exc)[:200]
        results.append((name, status, detail))
        print(f"{status:<5} {name:<11} {detail}", flush=True)

    def seed():
        history = ROOT / "data" / "seed" / "history.jsonl"
        if not history.exists():
            return "SKIP", f"{history.relative_to(ROOT)} missing (P1 generator output)"
        ok, tail = run(["scripts/seed.py", "--reset", "--api", api])
        return ("OK" if ok else "FAIL"), tail

    def frames():
        videos = sorted(p for p in RECORDINGS.glob("week[1-3].*") if p.is_file())
        if not videos:
            return (
                "SKIP",
                f"no recordings in {RECORDINGS.relative_to(ROOT)} (P2 shares them by drive)",
            )
        ok, tail = run(["scripts/video_to_frames.py", "--uc1", str(RECORDINGS), "--api-base", api])
        return ("OK" if ok else "FAIL"), tail

    def precompute():
        ok, tail = run(["scripts/precompute.py"])
        return ("OK" if ok else "FAIL"), tail

    def mocksite():
        return "OK", f"active {http(api, 'POST', '/demo/mocksite/v1')['active']}"

    def freeze():
        return "OK", set_env_flag("VOCAB_FROZEN", "1")

    def snap():
        current = snapshot(api)
        digest = hashlib.sha256(json.dumps(current, sort_keys=True).encode()).hexdigest()[:12]
        previous = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else None
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(json.dumps({"digest": digest, "state": current}, indent=2))
        summary = f"{len(current['tools'])} tools, {len(current['suggestions'])} suggestions, "
        summary += f"{len(current['declined'])} declined, digest {digest}"
        if current["missing"]:
            summary += f"; not live: {', '.join(current['missing'])}"
        if previous is None:
            return "OK", summary + " (first run, saved)"
        if previous["digest"] == digest:
            return "OK", summary + " (same as last reset)"
        return "WARN", summary + f" (differs from last reset {previous['digest']})"

    step(
        "init_db", lambda: (lambda r: ("OK" if r[0] else "FAIL", r[1]))(run(["scripts/init_db.py"]))
    )
    step("seed", seed)
    step("frames", frames)
    step("precompute", precompute)
    step("mocksite", mocksite)
    step("freeze", freeze)
    step("snapshot", snap)
    failed = [name for name, status, _ in results if status == "FAIL"]
    print("demo reset:", "FAILED " + ", ".join(failed) if failed else "done")
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--skip", default="", help=f"comma list of: {', '.join(STEPS)}")
    sys.exit(main(parser.parse_args()))
