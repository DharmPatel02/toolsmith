"""Forge step 1 (P2.1.4 + P2.1.8): pattern -> ToolSpec with `derivation`."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from app import llm
from app.forge.checks import ALLOWED_DEPS
from app.prompts.forge_prompts import SPEC_PROMPT, SPEC_SCHEMA

log = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[3]


def resolve_artifact(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else Path(os.getenv("ARTIFACTS_ROOT", REPO_ROOT)) / p


def profile_inputs(paths: list[str]) -> list[dict]:
    """Column names, dtypes and null counts of real past inputs (no cell values beyond 2 rows)."""
    import pandas as pd

    out = []
    for path in paths:
        f = resolve_artifact(path)
        try:
            df = pd.read_csv(f) if f.suffix == ".csv" else pd.read_excel(f)
        except Exception as e:  # noqa: BLE001 - a bad fixture shouldn't stop the forge
            log.warning("cannot profile %s: %s", f, e)
            continue
        out.append({
            "file": f.name, "rows": len(df), "columns": [str(c) for c in df.columns],
            "dtypes": {str(c): str(t) for c, t in df.dtypes.items()},
            "nulls": {str(c): int(n) for c, n in df.isna().sum().items() if n},
            "sample": json.loads(df.head(2).to_json(orient="records", date_format="iso")),
        })
    return out


def pattern_brief(pattern: dict) -> dict:
    keys = ("title", "signature", "static_steps", "dynamic_params", "support", "distinct_days",
            "periodicity", "avg_minutes", "observed_tier", "sources")
    return {k: pattern[k] for k in keys if k in pattern}


async def build_spec(pattern: dict, profiles: list[dict]) -> tuple[dict, llm.LLMResult]:
    user = ("PATTERN:\n" + json.dumps(pattern_brief(pattern), indent=1, default=str)
            + "\n\nINPUT PROFILES FROM PAST OCCURRENCES:\n" + json.dumps(profiles, indent=1, default=str))
    res = await llm.complete("heavy", [{"role": "system", "content": SPEC_PROMPT},
                                       {"role": "user", "content": user}], SPEC_SCHEMA)
    return normalize_spec(res.json, pattern), res


def normalize_spec(spec: dict, pattern: dict) -> dict:
    """Make the spec agree with the pattern and the allow-lists, whatever the model said."""
    spec = json.loads(json.dumps(spec))
    ps = spec.setdefault("params_schema", {"type": "object", "properties": {}})
    props = ps.setdefault("properties", {})
    required = ps.setdefault("required", [])
    for p in pattern.get("dynamic_params", []):
        name = p["name"]
        prop = props.setdefault(name, {"type": "string"})
        if p.get("type") == "file":
            prop.update({"type": "string", "format": "file"})
        if name not in required:
            required.append(name)

    req = spec.setdefault("requires", {})
    req["deps"] = [d for d in req.get("deps", []) if d.lower() in ALLOWED_DEPS]
    req.setdefault("tools", [])
    scopes = req.setdefault("scopes", [])
    if spec.get("outputs", {}).get("files") and "write:outputs" not in scopes:
        scopes.append("write:outputs")
    # what the tool may do in other apps comes from the observed steps, not from the model
    from app.automation.plan import automation_plan

    plan = automation_plan(pattern)
    for step in plan["steps"]:
        app = step["connector"]
        if app and app != "web" and f"app:{app}" not in scopes:
            scopes.append(f"app:{app}")
    spec["automation"] = [{k: step[k] for k in ("label", "automation", "connector")}
                          for step in plan["steps"]]

    der = spec.setdefault("derivation", {})
    if pattern.get("observed_tier"):
        der["observed_tier"] = pattern["observed_tier"]
    der.setdefault("observed_tier", "T0")
    der.setdefault("execution_path", "api")
    spec.setdefault("not_automatable", None)
    return spec


def input_names(spec: dict) -> list[str]:
    """Params that are files, i.e. mounted inputs rather than values."""
    props = spec.get("params_schema", {}).get("properties", {})
    return [n for n, p in props.items() if p.get("format") == "file"]
