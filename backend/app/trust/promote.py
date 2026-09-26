"""promote() (P2.2.3): an approved candidate becomes a tool version in ONE transaction.

Writes (all or nothing): tool_versions insert · tools upsert (pointer -> new version, trust
"dry_run", embedding) · verdict.tool_id · pattern -> "toolified" · candidate -> "approved".
The embedding is computed before the transaction (network call). Publishes `promoted`.
"""
from __future__ import annotations

import logging
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app import embeddings
from app.forge import deps

log = logging.getLogger(__name__)


class PromoteError(RuntimeError):
    pass


@dataclass
class Op:
    collection: str
    method: str            # insert_one | update_one
    args: tuple
    kwargs: dict = field(default_factory=dict)


async def promote(candidate_id: str, user_id: str) -> str:
    db = deps.get_db()
    cand = await db.candidates.find_one({"_id": candidate_id, "user_id": user_id})
    if not cand:
        raise PromoteError(f"candidate {candidate_id} not found for {user_id}")
    if cand["status"] != "passed":
        raise PromoteError(f"candidate {candidate_id} is '{cand['status']}', only 'passed' can be approved")

    existing = None
    if cand.get("tool_id"):  # heal / new version of an existing tool
        existing = await db.tools.find_one({"_id": cand["tool_id"]})
    else:
        existing = await db.tools.find_one({"user_id": user_id, "name": cand["spec"]["name"]})
    tool_id = existing["_id"] if existing else "tool_" + secrets.token_hex(4)
    version = (existing or {}).get("active_version", 0) + 1 if existing else 1
    vec = (await embeddings.embed([tool_embedding_text(cand)], "document"))[0]

    ops = plan_ops(cand, tool_id, version, vec, existing)
    await _run_in_transaction(db, ops)
    await deps.publish(user_id, "promoted", {"tool_id": tool_id, "candidate_id": candidate_id,
                                             "name": cand["spec"]["name"], "version": version,
                                             "trust": "dry_run"})
    return tool_id


def tool_embedding_text(cand: dict) -> str:
    spec = cand["spec"]
    return "\n".join(filter(None, [spec.get("title"), spec.get("purpose"), ", ".join(spec.get("keywords", [])),
                                   (cand.get("tutorial_md") or "")[:1500]]))


def plan_ops(cand: dict, tool_id: str, version: int, vec: list[float], existing: dict | None) -> list[Op]:
    now = datetime.now(UTC)
    spec = cand["spec"]
    origin = cand.get("origin") or {}
    tv = {
        "_id": f"{tool_id}@v{version}", "tool_id": tool_id, "user_id": cand["user_id"], "version": version,
        "code": cand["code"], "tests": cand["tests"], "params_schema": cand["params_schema"],
        "tutorial_md": cand.get("tutorial_md"), "requires": cand["requires"], "derivation": cand["derivation"],
        "spec": spec,
        "fixtures_ref": {"evidence_session_ids": origin.get("evidence_session_ids", []),
                         "evidence_inputs": cand.get("evidence_inputs", []),
                         "replay_cases": cand.get("replay_cases") or []},
        "created_from": {k: cand.get(k) for k in ("pattern_id", "idea_id") if cand.get(k)} | {"candidate_id": cand["_id"]},
        "verdict_id": cand.get("verdict_id"), "approved_at": now,
    }
    pointer = {
        "name": spec["name"], "title": spec.get("title", spec["name"]), "status": "active", "trust": "dry_run",
        "active_version": version, "keywords": spec.get("keywords", []), "embedding": vec,
        "embedding_model": embeddings.text_model(), "tier": spec.get("tier", "lean"),
        "derivation": cand["derivation"], "updated_at": now,
    }
    if existing:
        tool_op = Op("tools", "update_one", ({"_id": tool_id}, {"$set": pointer}))
    else:
        tool_op = Op("tools", "insert_one", ({
            "_id": tool_id, "user_id": cand["user_id"], **pointer, "created_at": now,
            "stats": {"runs": 0, "success": 0, "edited": 0, "p50_ms": None, "minutes_saved": 0},
            "baseline": {"success_rate": None, "window": 10}, "trust_history": [],
            "lineage": {"calls": [], "parents": [], "merged_from": [], "merged_into": None}},))
    ops = [Op("tool_versions", "insert_one", (tv,)), tool_op]
    if cand.get("verdict_id"):
        ops.append(Op("verdicts", "update_one", ({"_id": cand["verdict_id"]}, {"$set": {"tool_id": tool_id}})))
    if cand.get("pattern_id"):
        ops.append(Op("patterns", "update_one", ({"_id": cand["pattern_id"]},
                                                 {"$set": {"status": "toolified", "tool_id": tool_id}})))
    ops.append(Op("candidates", "update_one", ({"_id": cand["_id"], "status": "passed"},
                                               {"$set": {"status": "approved", "tool_id": tool_id,
                                                         "approved_at": now}})))
    return ops


async def apply_op(db: Any, op: Op, session: Any = None) -> None:
    res = await getattr(db[op.collection], op.method)(*op.args, session=session, **op.kwargs)
    if op.collection == "candidates" and getattr(res, "matched_count", 1) == 0:
        raise PromoteError("candidate changed during promotion")  # someone else approved/rejected it


async def _mongo_transaction(db: Any, ops: list[Op]) -> None:
    client = db.client
    async with await client.start_session() as s, s.start_transaction():
        for op in ops:
            await apply_op(db, op, session=s)


# Swappable for tests (mongomock has no sessions); production always uses a real transaction.
_run_in_transaction: Callable[[Any, list[Op]], Awaitable[None]] = _mongo_transaction


async def reject(candidate_id: str, user_id: str, reason: str | None = None) -> None:
    db = deps.get_db()
    res = await db.candidates.update_one(
        {"_id": candidate_id, "user_id": user_id, "status": {"$in": ["passed", "failed", "gating"]}},
        {"$set": {"status": "rejected", "rejected_reason": reason, "rejected_at": datetime.now(UTC)}})
    if res.matched_count == 0:
        raise PromoteError(f"candidate {candidate_id} cannot be rejected")
