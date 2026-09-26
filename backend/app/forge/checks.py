"""Static checks on forged code (P2.1.5): syntax, `run(ctx, **params)`, import allow-list,
dependency allow-list, banned builtins, ruff. Returns a list of problems ([] = pass)."""
from __future__ import annotations

import ast
import shutil
import subprocess
import sys

ALLOWED_IMPORTS = frozenset({
    "pandas", "numpy", "openpyxl", "json", "re", "math", "statistics", "datetime",
    "collections", "itertools", "bs4", "lxml", "plotly",
})
ALLOWED_DEPS = frozenset({"pandas", "numpy", "openpyxl", "bs4", "beautifulsoup4", "lxml", "plotly"})
BANNED_CALLS = frozenset({"open", "eval", "exec", "compile", "__import__", "input", "breakpoint",
                          "globals", "locals", "vars", "setattr", "delattr"})
# ruff: syntax errors, undefined names, bad comparisons; not style.
RUFF_SELECT = "E9,F63,F7,F82"


def check_tool_code(code: str, deps: list[str] | None = None) -> list[str]:
    problems = _check_source(code, "tool code")
    if problems and problems[0].startswith("tool code: syntax"):
        return problems
    tree = ast.parse(code)
    run = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run"), None)
    if run is None:
        problems.append("tool code: no top-level `def run(ctx, **params)`")
    elif not run.args.args or run.args.args[0].arg != "ctx":
        problems.append("tool code: `run` must take `ctx` as its first argument")
    for d in deps or []:
        if d.split("==")[0].split(">=")[0].strip().lower() not in ALLOWED_DEPS:
            problems.append(f"dependency not allowed: {d}")
    return problems


def check_tests(tests: str) -> list[str]:
    problems = _check_source(tests, "tests", known_names={"run", "FakeCtx"})
    if not problems:
        tree = ast.parse(tests)
        if not any(isinstance(n, ast.FunctionDef) and n.name.startswith("test_") for n in tree.body):
            problems.append("tests: no `def test_...()` function")
    return problems


def _check_source(src: str, label: str, known_names: set[str] | None = None) -> list[str]:
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [f"{label}: syntax error line {e.lineno}: {e.msg}"]
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [node.module or ""] if node.level == 0 else ["<relative>"]
        else:
            mods = []
        for m in mods:
            if m.split(".")[0] not in ALLOWED_IMPORTS:
                problems.append(f"{label}: import not allowed: {m} (line {node.lineno})")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BANNED_CALLS:
            problems.append(f"{label}: call not allowed: {node.func.id}() (line {node.lineno})")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr != "__name__":
            problems.append(f"{label}: dunder attribute not allowed: {node.attr} (line {node.lineno})")
    problems += _ruff(src, label, known_names or set())
    return problems


def _ruff(src: str, label: str, known_names: set[str]) -> list[str]:
    cmd = [sys.executable, "-m", "ruff"] if not shutil.which("ruff") else ["ruff"]
    # Names provided at run time (e.g. `run`, `FakeCtx` in tests) are declared as builtins.
    builtins = ",".join(f'"{n}"' for n in sorted(known_names))
    args = [*cmd, "check", "--isolated", "--select", RUFF_SELECT, "--output-format", "concise",
            "--config", f"builtins=[{builtins}]", "--stdin-filename", "tool.py", "-"]
    proc = subprocess.run(args, input=src, capture_output=True, text=True, timeout=30, check=False)
    if proc.returncode == 0:
        return []
    lines = [ln.split("tool.py:", 1)[-1].strip() for ln in proc.stdout.splitlines() if "tool.py:" in ln]
    return [f"{label}: ruff {ln}" for ln in lines] or [f"{label}: ruff failed: {proc.stderr.strip()[:200]}"]
