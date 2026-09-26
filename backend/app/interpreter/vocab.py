"""Interpreter Stage D: canonical verbs via `action_vocab`, then canonical signatures.

- verbs in the vocab pass through
- "other" + proposed_verb: alias to an existing verb if cosine >= 0.88, else a `candidate`
  entry that becomes `active` after 3 sightings
- VOCAB_FROZEN=1 (set by demo_reset) stops all vocab writes: an unstable vocab silently
  destroys support counts
"""
from __future__ import annotations

import os
from datetime import UTC, datetime

from app import embeddings
from app.forge import deps

VOCAB_ALIAS_MIN = 0.88
VOCAB_PROMOTE_AFTER = 3

# Used only when action_vocab is empty (P1 seeds data/action_vocab_seed.json). Plan §6.0.5.
DEFAULT_VERBS = [
    "file.open", "file.save", "file.download", "file.upload",
    "table.rename", "table.dropna", "table.cast", "table.pivot", "table.filter", "table.sort",
    "table.join", "table.dedupe", "table.formula",
    "chart.bar", "chart.line", "chart.pie",
    "web.navigate", "web.fetch", "web.extract", "web.submit", "web.search",
    "doc.read", "doc.extract",
    "export.html", "export.pdf", "export.csv", "msg.send",
]


def frozen() -> bool:
    return os.getenv("VOCAB_FROZEN", "").lower() in {"1", "true", "yes"}


async def load_vocab() -> list[dict]:
    docs = [d async for d in deps.get_db().action_vocab.find({})]
    return docs or [{"_id": v, "status": "active", "aliases": []} for v in DEFAULT_VERBS]


def active_verbs(vocab: list[dict]) -> list[str]:
    return sorted(d["_id"] for d in vocab if d.get("status", "active") == "active")


async def canonicalize(steps: list[dict], vocab: list[dict]) -> list[dict]:
    """Resolve "other" steps against the vocab (alias / candidate), in place. Returns steps."""
    others = [s for s in steps if s["verb"] == "other" and s.get("proposed_verb")]
    if not others:
        return steps
    active = [d for d in vocab if d.get("status", "active") == "active"]
    texts = [_vocab_text(d) for d in active]
    vecs = await embeddings.embed(texts + [_proposal_text(s) for s in others], "document")
    vocab_vecs, prop_vecs = vecs[:len(active)], vecs[len(active):]
    db = deps.get_db()
    for s, pv in zip(others, prop_vecs, strict=True):
        best, score = None, -1.0
        for d, vv in zip(active, vocab_vecs, strict=True):
            sim = embeddings.cosine(pv, vv)
            if sim > score:
                best, score = d, sim
        proposed = s["proposed_verb"].strip().lower()
        if best is not None and score >= VOCAB_ALIAS_MIN:
            s["verb"], s["aliased_from"] = best["_id"], proposed
            if not frozen():
                await db.action_vocab.update_one({"_id": best["_id"]}, {"$addToSet": {"aliases": proposed}},
                                                 upsert=True)
        elif not frozen():
            now = datetime.now(UTC)
            await db.action_vocab.update_one(
                {"_id": proposed},
                {"$inc": {"seen": 1}, "$setOnInsert": {"status": "candidate", "aliases": [], "first_seen": now},
                 "$addToSet": {"example_frames": s["frame_id"]}}, upsert=True)
            doc = await db.action_vocab.find_one({"_id": proposed})
            if doc and doc.get("status") == "candidate" and doc.get("seen", 0) >= VOCAB_PROMOTE_AFTER:
                await db.action_vocab.update_one({"_id": proposed}, {"$set": {"status": "active"}})
    return steps


def _vocab_text(d: dict) -> str:
    return d["_id"].replace(".", " ") + ((": " + ", ".join(d.get("aliases", []))) if d.get("aliases") else "")


def _proposal_text(s: dict) -> str:
    target = (s.get("target") or {}).get("name") or ""
    return f"{s['proposed_verb'].replace('.', ' ')} {target}".strip()


def signature(verb: str, args_shape: dict) -> str:
    """Canonical `domain.verb:argshape`. P1's mapper (app.miner.signatures) when merged."""
    try:
        from app.miner.signatures import to_signature  # P1
    except ImportError:
        return fallback_signature(verb, args_shape)
    return to_signature(verb, args_shape)


def fallback_signature(verb: str, args_shape: dict) -> str:
    """Same rules as the UC1 fixture signature: file.open:xlsx, table.rename:cols, table.pivot:2col."""
    a = {str(k).lower(): v for k, v in (args_shape or {}).items()}
    if verb == "other":
        return "other"
    if verb.startswith("file.") and (ext := a.get("ext") or a.get("extension")):
        return f"{verb}:{str(ext).lower().lstrip('.')}"
    if verb == "table.rename":
        return "table.rename:cols"
    if verb == "table.pivot":
        n = sum(1 for k in ("rows", "index", "columns", "values") if a.get(k))
        return f"table.pivot:{max(n, 2)}col"
    if verb == "web.fetch":
        return "web.fetch:html"
    if verb == "web.extract":
        return "web.extract:list"
    if verb == "web.submit":
        return "web.submit:form"
    return verb
