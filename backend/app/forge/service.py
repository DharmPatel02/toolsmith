"""Forge service (P2.1.7): pattern -> spec -> code + tests -> TOOL.md -> `candidates` doc.

The gate runs after this (see forge/jobs.py). Publishes `forge_started` and `forged`.
"""
from __future__ import annotations

import logging
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path

from app import llm
from app.forge import deps
from app.forge.codegen import generate_code
from app.forge.spec import build_spec, normalize_spec, profile_inputs
from app.forge.tutorial import write_tutorial

log = logging.getLogger(__name__)


class ForgeError(RuntimeError):
    pass


async def forge_from_pattern(pattern_id: str) -> str:
    pattern = await deps.get_db().patterns.find_one({"_id": pattern_id})
    if not pattern:
        raise ForgeError(f"pattern {pattern_id} not found")
    return await forge_from_pattern_doc(pattern)


def new_candidate_id() -> str:
    return "cand_" + secrets.token_hex(4)


async def forge_from_pattern_doc(pattern: dict, candidate_id: str | None = None) -> str:
    """Forge from a pattern document (also used by POST /dev/forge with a fixture)."""
    origin = {"pattern_id": pattern.get("_id"), "title": pattern.get("title"),
              "signature": pattern.get("signature", []),
              "evidence_session_ids": pattern.get("evidence_session_ids", [])}
    return await _forge(pattern["user_id"], pattern, origin, spec=None, cid=candidate_id)


async def forge_from_spec(user_id: str, spec: dict, origin: dict) -> str:
    """Forge from a ready spec (concierge idea, heal). `origin` may carry a `pattern` dict."""
    return await _forge(user_id, origin.get("pattern") or {}, origin, spec=spec)


async def _forge(user_id: str, pattern: dict, origin: dict, spec: dict | None, cid: str | None = None) -> str:
    cid = cid or new_candidate_id()
    t0 = time.monotonic()
    await deps.publish(user_id, "forge_started", {"candidate_id": cid, "pattern_id": origin.get("pattern_id"),
                                                  "title": origin.get("title")})
    usage: list[llm.LLMResult] = []
    doc = {"_id": cid, "user_id": user_id, "pattern_id": origin.get("pattern_id"),
           "idea_id": origin.get("idea_id"), "origin": origin, "verdict_id": None,
           "created_at": datetime.now(UTC)}
    try:
        paths = await evidence_inputs(pattern)
        profiles = profile_inputs(paths)
        if spec is None:
            spec, res = await build_spec(pattern, profiles)
            usage.append(res)
        else:
            spec = normalize_spec(spec, pattern)
        doc.update(spec=spec, params_schema=spec["params_schema"], requires=spec["requires"],
                   derivation=spec["derivation"], not_automatable=spec.get("not_automatable"),
                   evidence_inputs=paths)

        if spec.get("not_automatable"):
            doc.update(status="failed", code=None, tests=None, tutorial_md=None,
                       problems=[f"not automatable: {spec['not_automatable'].get('reason')}"])
        else:
            code = await generate_code(spec, pattern, profiles)
            usage += code.usage
            doc.update(code=code.code, tests=code.tests, problems=code.problems, attempts=code.attempts,
                       status="gating" if code.ok else "failed")
            example = {"inputs": example_inputs(spec, paths)}
            doc["tutorial_md"], tut_usage = await write_tutorial(spec, example)
            usage += tut_usage
    except Exception as e:
        log.exception("forge %s failed", cid)
        doc.update(status="failed", problems=[f"forge error: {e}"])

    doc["cost"] = cost_of(usage)
    doc["forge_ms"] = int((time.monotonic() - t0) * 1000)
    await deps.get_db().candidates.insert_one(doc)
    await deps.publish(user_id, "forged", {
        "candidate_id": cid, "pattern_id": origin.get("pattern_id"), "status": doc["status"],
        "name": (doc.get("spec") or {}).get("name"),
        "execution_path": (doc.get("derivation") or {}).get("execution_path"),
        "problems": doc.get("problems", [])[:5]})
    return cid


async def evidence_inputs(pattern: dict) -> list[str]:
    """Input file paths from the pattern's evidence sessions (`sessions.artifacts.inputs`).
    Falls back to `pattern.artifact_paths` (dev fixtures)."""
    ids = pattern.get("evidence_session_ids") or []
    paths: list[str] = []
    if ids:
        async for s in deps.get_db().sessions.find({"_id": {"$in": ids}}, {"artifacts": 1}):
            for item in (s.get("artifacts") or {}).get("inputs", []):
                p = item.get("path") if isinstance(item, dict) else item
                if p and p not in paths:
                    paths.append(p)
    return paths or list(pattern.get("artifact_paths", []))


def example_inputs(spec: dict, paths: list[str]) -> dict:
    props = spec.get("params_schema", {}).get("properties", {})
    ex = {}
    for name, p in props.items():
        if p.get("format") == "file" and paths:
            ex[name] = Path(paths[0]).name
        elif "example" in p:
            ex[name] = p["example"]
    return ex


def cost_of(usage: list[llm.LLMResult]) -> dict:
    return {"tokens_in": sum(u.tokens_in for u in usage), "tokens_out": sum(u.tokens_out for u in usage),
            "usd": round(sum(u.usd for u in usage), 6), "calls": len(usage),
            "cached_calls": sum(1 for u in usage if u.cached)}
