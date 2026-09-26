"""P2.1.2 / P2.1.3 isolation: raw sockets refused without a net: scope, recorded pages for replay,
and the Docker command carries every limit (the Docker run itself needs Docker on the machine)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.sandbox import runner
from app.sandbox.harness import FETCH_MAP_INPUT

RAW_SOCKET = '''
import socket

def run(ctx):
    socket.create_connection(("example.com", 80), timeout=2)
    return {"reached": True}
'''

FETCHER = '''
def run(ctx, url):
    return {"html": ctx.fetch(url)}
'''


@pytest.fixture(autouse=True)
def process_backend(monkeypatch):
    monkeypatch.setenv("SANDBOX_BACKEND", "process")


@pytest.mark.asyncio
async def test_raw_socket_blocked_without_net_scope():
    r = await runner.run_in_sandbox(RAW_SOCKET, "run", {}, {}, "dry_run", [])
    assert not r.ok and "net:<domain> scope" in r.error


@pytest.mark.asyncio
async def test_fetch_map_replays_recorded_page_and_keeps_scope_check():
    fm = {FETCH_MAP_INPUT: json.dumps({"http://shop.test/": "<p>v2</p>"})}
    r = await runner.run_in_sandbox(FETCHER, "run", {"url": "http://shop.test/"}, fm, "dry_run", ["net:shop.test"])
    assert r.ok and r.output == {"html": "<p>v2</p>"}
    r = await runner.run_in_sandbox(FETCHER, "run", {"url": "http://shop.test/"}, fm, "dry_run", [])
    assert not r.ok and "net:shop.test" in r.error


def test_docker_command_limits(tmp_path):
    cmd = runner._docker_command(tmp_path, {"entry": "run", "params": {}, "mode": "dry_run", "scopes": []},
                                 [], "sbx1")
    joined = " ".join(cmd)
    for flag in ("--network none", "--read-only", "--memory 512m", "--pids-limit 128", "--cap-drop ALL",
                 f"{tmp_path}:/job:ro"):
        assert flag in joined
    cfg = json.loads(cmd[-1])
    assert cfg["input_dir"] == "/job/inputs" and cfg["tool_path"] == "/job/tool_under_test.py"
    net = runner._docker_command(tmp_path, {}, ["net:localhost"], "sbx2")
    assert "--network" in net and net[net.index("--network") + 1] == "bridge"


def test_dockerfile_installs_only_the_allow_list():
    text = (Path(__file__).resolve().parents[4] / "sandbox" / "Dockerfile").read_text()
    assert "python:3.11-slim" in text and "USER sandbox" in text
    for pkg in ("pandas", "numpy", "openpyxl", "beautifulsoup4", "lxml", "plotly"):
        assert pkg in text
    assert "curl" not in text


@pytest.mark.skipif(not shutil.which("docker"), reason="Docker not installed")
@pytest.mark.asyncio
async def test_docker_network_none(monkeypatch):
    img = subprocess.run(["docker", "image", "inspect", runner._image()], capture_output=True, check=False)
    if img.returncode:
        pytest.skip("sandbox image not built: docker build -t toolsmith-sandbox:latest sandbox/")
    monkeypatch.setenv("SANDBOX_BACKEND", "docker")
    r = await runner.run_in_sandbox("import pandas\n\ndef run(ctx):\n    return {'v': pandas.__version__}",
                                    "run", {}, {}, "dry_run", [])
    assert r.ok, r.error
    r = await runner.run_in_sandbox(RAW_SOCKET.replace("import socket", "import socket, sys"), "run", {}, {},
                                    "dry_run", [])
    assert not r.ok
