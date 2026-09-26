from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


@dataclass(slots=True)
class Write:
    path: str
    kind: str
    bytes: int


@dataclass(slots=True)
class SandboxResult:
    ok: bool
    output: dict[str, Any]
    intended_writes: list[Write]
    stdout: str
    error: str | None
    duration_ms: int


async def run_in_sandbox(
    code: str,
    entry: str,
    params: dict,
    inputs: dict[str, str],
    mode: Literal["dry_run", "live"],
    scopes: list[str],
    timeout_s: int = 30,
    deps: dict[str, str] | None = None,
) -> SandboxResult:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="toolsmith-sandbox-") as tmp:
        root = Path(tmp)
        input_dir = root / "inputs"
        output_dir = root / "outputs"
        tools_dir = root / "tools"
        input_dir.mkdir()
        output_dir.mkdir()
        tools_dir.mkdir()

        _materialize_inputs(input_dir, inputs)
        _materialize_deps(tools_dir, deps or {})
        tool_path = root / "tool_under_test.py"
        tool_path.write_text(code, encoding="utf-8")
        bootstrap_path = root / "bootstrap.py"
        bootstrap_path.write_text(_bootstrap_source(), encoding="utf-8")

        command = [
            sys.executable,
            str(bootstrap_path),
            json.dumps(
                {
                    "tool_path": str(tool_path),
                    "entry": entry,
                    "params": params,
                    "mode": mode,
                    "scopes": scopes,
                    "input_dir": str(input_dir),
                    "output_dir": str(output_dir),
                    "tools_dir": str(tools_dir),
                }
            ),
        ]
        env = {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": os.pathsep.join([str(Path(__file__).parent), str(root), str(tools_dir)]),
        }
        try:
            proc = subprocess.run(
                command,
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return SandboxResult(
                ok=False,
                output={},
                intended_writes=[],
                stdout=exc.stdout or "",
                error=f"timeout after {timeout_s}s",
                duration_ms=_elapsed_ms(started),
            )

        payload, parse_error = _parse_result(proc.stdout)
        if proc.returncode != 0 or parse_error:
            return SandboxResult(
                ok=False,
                output={},
                intended_writes=[],
                stdout=proc.stdout,
                error=parse_error or proc.stderr.strip() or f"exit code {proc.returncode}",
                duration_ms=_elapsed_ms(started),
            )

        return SandboxResult(
            ok=bool(payload.get("ok")),
            output=payload.get("output") or {},
            intended_writes=[Write(**item) for item in payload.get("intended_writes", [])],
            stdout=payload.get("stdout", ""),
            error=payload.get("error"),
            duration_ms=_elapsed_ms(started),
        )


def _materialize_inputs(input_dir: Path, inputs: dict[str, str]) -> None:
    for name, value in inputs.items():
        dest = (input_dir / name).resolve()
        if not str(dest).startswith(str(input_dir.resolve())):
            raise PermissionError(f"input path escapes sandbox: {name}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = Path(value)
        if src.exists() and src.is_file():
            shutil.copyfile(src, dest)
        else:
            dest.write_text(value, encoding="utf-8")


def _materialize_deps(tools_dir: Path, deps: dict[str, str]) -> None:
    for name, source in deps.items():
        if not name.replace("_", "").isalnum():
            raise ValueError(f"invalid dependency name: {name}")
        (tools_dir / f"{name}.py").write_text(source, encoding="utf-8")


def _parse_result(stdout: str) -> tuple[dict[str, Any], str | None]:
    marker = "__TOOLSMITH_SANDBOX_RESULT__="
    for line in reversed(stdout.splitlines()):
        if line.startswith(marker):
            return json.loads(line[len(marker) :]), None
    return {}, "sandbox result marker missing"


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _bootstrap_source() -> str:
    return r'''
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import traceback
from pathlib import Path

from harness import SandboxContext, writes_to_dicts


def main() -> None:
    cfg = json.loads(sys.argv[1])
    sys.path.insert(0, cfg["tools_dir"])
    ctx = SandboxContext(
        mode=cfg["mode"],
        scopes=cfg["scopes"],
        inputs_dir=Path(cfg["input_dir"]),
        output_dir=Path(cfg["output_dir"]),
    )
    output = {}
    error = None
    ok = False
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            spec = importlib.util.spec_from_file_location("tool_under_test", cfg["tool_path"])
            module = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(module)
            fn = getattr(module, cfg["entry"])
            value = fn(ctx, cfg["params"])
            output = value if isinstance(value, dict) else {"result": value}
        ok = True
    except Exception:
        error = traceback.format_exc()
    result = {
        "ok": ok,
        "output": output,
        "intended_writes": writes_to_dicts(ctx.intended_writes),
        "stdout": captured.getvalue(),
        "error": error,
    }
    print("__TOOLSMITH_SANDBOX_RESULT__=" + json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
'''
