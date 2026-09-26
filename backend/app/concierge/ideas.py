"""analyze_idea (P4.2.4): "I keep doing X, automate it?" -> use existing tool Y, or a refined spec.

Plan §6.4 M4: (1) hybrid search: is it already covered? (2) feasibility, scopes, deps (lean LLM,
JSON schema); (3) savings estimate from history (recall_episodes); (4) spec or "use tool Y".
If the user confirms, the stored spec goes to `forge_from_spec`. Ideas persist in `ideas`.
"""

from __future__ import annotations

import os
import re
import secrets
from datetime import UTC, datetime
from typing import Any

from app import llm
from app.forge import deps

COVERED_MIN_SCORE = 0.82  # policy T_high default; a weaker hit is "related", not "covered"
ALLOWED_DEPS = {"pandas", "numpy", "openpyxl", "bs4", "lxml", "plotly"}

IDEA_PROMPT = """\
You turn a user's automation idea into a tool spec for ToolSmith. Tools are Python functions
`run(ctx, **params)` that read named input files, may fetch only allow-listed domains, and write
outputs only through ctx (a dry run shows the writes first). Allowed libraries: pandas, numpy,
openpyxl, bs4, lxml, plotly, and the standard library.

Sites the user has allow-listed (tools may fetch these with ctx.fetch): {sites}.
Reading those pages, parsing tables and writing a report/CSV/HTML IS automatable.

Decide if the idea is automatable this way. If it needs a human judgement, a login, payments or
sending messages without review, set feasible=false and explain in not_automatable_reason.
Make anything that could change between runs a param (URLs, thresholds, input files, dates).
List every library the code needs in deps (bs4 for HTML, pandas for tables, openpyxl for xlsx).
Scopes: "read:files", "write:outputs", "net:<domain>". Keep names snake_case. Do not invent
facts about the user; estimate minutes_per_run only from the idea text (null if unknown)."""

IDEA_SCHEMA = {
    "type": "object",
    "properties": {
        "feasible": {"type": "boolean"},
        "not_automatable_reason": {"type": ["string", "null"]},
        "name": {"type": "string"},
        "title": {"type": "string"},
        "purpose": {"type": "string"},
        "params": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": ["string", "number", "integer", "boolean", "file"],
                    },
                    "description": {"type": "string"},
                },
                "required": ["name", "type"],
            },
        },
        "outputs": {"type": "object"},
        "scopes": {"type": "array", "items": {"type": "string"}},
        "deps": {"type": "array", "items": {"type": "string"}},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "minutes_per_run": {"type": ["number", "null"]},
        "runs_per_week": {"type": ["number", "null"]},
    },
    "required": ["feasible", "name", "purpose", "params", "scopes", "deps"],
}


def _score(hit: Any) -> float:
    return float(hit["score"] if isinstance(hit, dict) else getattr(hit, "score", 0.0))


def _get(hit: Any, key: str) -> Any:
    return hit.get(key) if isinstance(hit, dict) else getattr(hit, key, None)


def to_tool_spec(draft: dict) -> dict:
    """LLM draft -> ToolSpec shape (contracts.ToolSpec), with deps clamped to the allow-list."""
    props = {}
    for p in draft.get("params") or []:
        name = re.sub(r"\W+", "_", str(p.get("name", "")).strip()).strip("_").lower()
        if not name:
            continue
        kind = p.get("type", "string")
        props[name] = {
            "type": "string" if kind == "file" else kind,
            "description": p.get("description", ""),
        }
        if kind == "file":
            props[name]["format"] = "file"
    deps_ = sorted({d for d in draft.get("deps") or [] if d in ALLOWED_DEPS})
    name = re.sub(r"\W+", "_", draft.get("name") or "new_tool").strip("_").lower() or "new_tool"
    reason = draft.get("not_automatable_reason")
    return {
        "name": name,
        "purpose": draft.get("purpose") or draft.get("title") or name,
        "params_schema": {
            "type": "object",
            "properties": props,
            "required": list(props),
            "additionalProperties": False,
        },
        "outputs": draft.get("outputs") or {},
        "requires": {
            "scopes": list(dict.fromkeys(draft.get("scopes") or [])),
            "deps": deps_,
            "tools": [],
        },
        "keywords": draft.get("keywords") or [],
        "derivation": {"observed_tier": "T0", "execution_path": "api"},
        "not_automatable": None
        if draft.get("feasible", True)
        else {"reason": reason or "needs a human step"},
    }


def savings_from_history(episodes: list, draft: dict) -> float:
    """Minutes/week: from matching past episodes if any, else the model's own estimate."""
    relevant = [e for e in episodes if _score(e) >= 0.7]
    if relevant:
        weeks = set()
        for e in relevant:
            try:
                weeks.add(datetime.fromisoformat(str(_get(e, "date"))[:10]).isocalendar()[:2])
            except ValueError:
                weeks.add(str(_get(e, "date")))
        minutes = sum(float(_get(e, "minutes") or 0) for e in relevant)
        return round(minutes / max(1, len(weeks)), 1)
    per_run = draft.get("minutes_per_run") or 0
    per_week = draft.get("runs_per_week") or 1
    return round(float(per_run) * float(per_week), 1)


async def analyze_idea(
    user_id: str, text: str, *, confirm: bool = False, idea_id: str | None = None
) -> dict:
    """Returns IdeaAnalysis + {idea_id, candidate_id?, related_tool_id?}."""
    db = deps.get_db()
    if idea_id and confirm:
        stored = await db.ideas.find_one({"_id": idea_id, "user_id": user_id})
        if stored and stored.get("analysis", {}).get("spec"):
            return await _confirm(user_id, stored)

    hits = await deps.search_tools(user_id, text, 3)
    top = hits[0] if hits else None
    if top is not None and _score(top) >= COVERED_MIN_SCORE:
        analysis = {
            "covered_by_tool_id": _get(top, "tool_id"),
            "feasible": True,
            "scopes": [],
            "deps": [],
            "est_minutes_saved_week": 0.0,
            "spec": None,
        }
        return await _store(user_id, text, analysis, extra={"covered_score": _score(top)})

    sites = os.getenv("CAPTURE_ALLOWED_ORIGINS") or os.getenv("MOCKSITE_URL") or "none"
    prompt = IDEA_PROMPT.replace("{sites}", sites)
    res = await llm.complete(
        "lean",
        [{"role": "system", "content": prompt}, {"role": "user", "content": text}],
        IDEA_SCHEMA,
        max_tokens=1200,
    )
    draft = res.json or {}
    spec = to_tool_spec(draft)
    episodes = await deps.recall_episodes(user_id, text, 5)
    analysis = {
        "covered_by_tool_id": None,
        "feasible": bool(draft.get("feasible")),
        "scopes": spec["requires"]["scopes"],
        "deps": spec["requires"]["deps"],
        "est_minutes_saved_week": savings_from_history(episodes, draft),
        "spec": spec if draft.get("feasible") else None,
    }
    extra = {
        "related_tool_id": _get(top, "tool_id") if top is not None else None,
        "title": draft.get("title"),
        "reason": None
        if draft.get("feasible")
        else draft.get("not_automatable_reason") or "needs a human step",
    }
    stored = await _store(
        user_id, text, analysis, extra=extra, tokens=res.tokens_in + res.tokens_out
    )
    if confirm and analysis["spec"]:
        return await _confirm(user_id, await db.ideas.find_one({"_id": stored["idea_id"]}))
    return stored


async def _store(
    user_id: str, text: str, analysis: dict, *, extra: dict | None = None, tokens: int = 0
) -> dict:
    idea_id = "idea_" + secrets.token_hex(4)
    await deps.get_db().ideas.insert_one(
        {
            "_id": idea_id,
            "user_id": user_id,
            "text": text,
            "analysis": analysis,
            "status": "analyzed",
            "tokens": tokens,
            "created_at": datetime.now(UTC),
            **(extra or {}),
        }
    )
    return {
        **analysis,
        "idea_id": idea_id,
        **{k: v for k, v in (extra or {}).items() if v is not None},
    }


async def _confirm(user_id: str, stored: dict) -> dict:
    """User said yes: hand the spec to the forge (P2). Nothing is built without this step."""
    from app.forge.service import forge_from_spec

    analysis = stored["analysis"]
    cid = await forge_from_spec(
        user_id, analysis["spec"], {"idea_id": stored["_id"], "title": stored.get("title")}
    )
    await deps.get_db().ideas.update_one(
        {"_id": stored["_id"]}, {"$set": {"status": "forging", "candidate_id": cid}}
    )
    return {**analysis, "idea_id": stored["_id"], "candidate_id": cid}
