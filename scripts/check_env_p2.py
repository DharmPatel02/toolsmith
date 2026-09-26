"""P2.0.1: is this laptop ready for P2? Prints OK / FAIL / WARN per item; exit 1 on any FAIL.

    python scripts/check_env_p2.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE = os.getenv("SANDBOX_IMAGE", "toolsmith-sandbox:latest")
results: list[tuple[str, str, str]] = []


def check(name: str, status: str, note: str = "") -> None:
    results.append((status, name, note))


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        load_dotenv(ROOT / "backend" / ".env")
    except ImportError:
        pass

    check("python >= 3.11", "OK" if sys.version_info >= (3, 11) else "FAIL", sys.version.split()[0])
    ff = shutil.which("ffmpeg")
    check("ffmpeg on PATH", "OK" if ff else "FAIL", ff or "install ffmpeg (video_to_frames)")

    if not shutil.which("docker"):
        check("docker CLI", "WARN", "not installed: sandbox falls back to the process backend (no OS isolation)")
    else:
        check("docker CLI", "OK")
        if run(["docker", "image", "inspect", IMAGE]).returncode:
            check(f"image {IMAGE}", "WARN", f"build it: docker build -t {IMAGE} sandbox/")
        else:
            check(f"image {IMAGE}", "OK")
            ok = run(["docker", "run", "--rm", "--network", "none", IMAGE, "python", "-c", "import pandas"])
            check("network=none container imports pandas", "OK" if ok.returncode == 0 else "FAIL",
                  ok.stderr.strip()[-200:])
            net = run(["docker", "run", "--rm", "--network", "none", IMAGE, "python", "-c",
                       "import urllib.request as u; u.urlopen('http://example.com', timeout=3)"])
            check("network=none blocks the network", "OK" if net.returncode != 0 else "FAIL")

    for mod in ("litellm", "voyageai", "jsonschema", "PIL", "imagehash", "rapidocr_onnxruntime", "bs4", "motor",
                "pandas", "openpyxl", "fastapi", "httpx"):
        try:
            __import__(mod)
            check(f"import {mod}", "OK")
        except ImportError as e:
            check(f"import {mod}", "FAIL", str(e))

    for var, why in (("MONGODB_URI", "Atlas"), ("LLM_LEAN_MODEL", "lean tier"), ("LLM_HEAVY_MODEL", "forge / heal"),
                     ("LLM_VISION_MODEL", "interpreter"), ("VOYAGE_API_KEY", "real embeddings (else fake)"),
                     ("VOYAGE_MM_MODEL", "frame embeddings")):
        check(f"env {var}", "OK" if os.getenv(var) else "WARN", "" if os.getenv(var) else f"unset: {why}")
    if not (os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")):
        check("env OPENAI_API_KEY / OPENROUTER_API_KEY", "WARN", "no model key: only cached LLM calls work")

    width = max(len(n) for _, n, _ in results)
    for status, name, note in results:
        print(f"{status:<4}  {name:<{width}}  {note}")
    return 1 if any(s == "FAIL" for s, _, _ in results) else 0


if __name__ == "__main__":
    sys.exit(main())
