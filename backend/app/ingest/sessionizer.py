"""Deterministic batch/live sessionization, independent of the persistence adapter."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from app.contracts import Observation, Session

IDLE = timedelta(minutes=30)
APP_SHIFT = timedelta(minutes=3)


def _app(event: Observation) -> str:
    return str(event.target.get("app") or event.target.get("window_title") or event.meta.source)


def _tokens(text: str) -> set[str]:
    return {item.lower() for item in text.replace("·", " ").split() if item}


def _intent_cosine(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 1.0
    return len(a & b) / ((len(a) * len(b)) ** 0.5)


def _should_split_for_app_shift(group: list[Observation], event: Observation) -> bool:
    if not group:
        return False
    seen = {_app(item) for item in group}
    app = _app(event)
    if app in seen or event.ts - group[-1].ts <= APP_SHIFT:
        return False
    prior_intent = " ".join(item.intent_text for item in group if item.intent_text)
    return _intent_cosine(prior_intent, event.intent_text) < 0.5


async def sessionize(
    events: list[Observation],
    embed,
    *,
    now: datetime | None = None,
    embedding_model: str = "fixture",
    previous: list[Session] | None = None,
) -> list[Session]:
    now = now or datetime.now(timezone.utc)
    cached = {s.id: s for s in previous or []}
    streams = defaultdict(list)
    for event in events:
        # Supplied capture/replay session IDs preserve links to evidence and artifacts.
        streams[(event.meta.user_id, event.session_id)].append(event)
    sessions = []
    for (user_id, supplied_id), stream in sorted(streams.items(), key=lambda item: str(item[0])):
        groups = []
        for event in sorted(stream, key=lambda item: item.ts):
            if (
                not groups
                or event.ts - groups[-1][-1].ts >= IDLE
                or _should_split_for_app_shift(groups[-1], event)
            ):
                groups.append([])
            groups[-1].append(event)
        for index, group in enumerate(groups):
            start, end = group[0].ts, group[-1].ts
            seed = f"{user_id}:{supplied_id}:{start.isoformat()}"
            session_id = (
                supplied_id
                if supplied_id and index == 0
                else "s_" + sha256(seed.encode()).hexdigest()[:20]
            )
            for event in group:
                event.session_id = session_id
            eligible = [
                event
                for event in group
                if not event.evidence.needs_review and event.evidence.confidence >= 0.6
            ]
            texts = list(
                dict.fromkeys(event.intent_text for event in eligible if event.intent_text)
            )
            summary = " · ".join(texts)[:2000]
            closed = index < len(groups) - 1 or now - end >= IDLE
            old = cached.get(session_id)
            reusable = (
                old is not None
                and old.intent_summary == summary
                and old.embedding_model == embedding_model
                and old.intent_embedding
            )
            vectors = (
                ([old.intent_embedding] if reusable else await embed([summary])) if closed else []
            )
            if closed and (len(vectors) != 1 or not vectors[0]):
                raise ValueError("Embedding provider returned an invalid session vector")
            artifacts = {
                key: sorted({path for event in group for path in event.artifacts.get(key, [])})
                for key in ("inputs", "outputs")
            }
            duration = max(
                (end - start).total_seconds() / 60,
                sum(event.duration_ms for event in group) / 60000,
            )
            sessions.append(
                Session(
                    _id=session_id,
                    user_id=user_id,
                    started_at=start,
                    ended_at=end,
                    status="closed" if closed else "open",
                    source=group[0].meta.source,
                    signature_seq=[event.signature for event in eligible],
                    intent_summary=summary,
                    intent_embedding=vectors[0] if vectors else [],
                    embedding_model=embedding_model if closed else None,
                    minutes=duration,
                    tokens=sum(e.cost.tokens for e in group),
                    artifacts=artifacts,
                    outcome="error" if any(e.error for e in group) else "ok",
                )
            )
    return sessions
