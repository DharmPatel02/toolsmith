"""Mine closed episodes, score recurrence, and persist candidate/declined patterns."""

import hashlib
import json
from datetime import datetime, timezone
from statistics import mean

from app.config import ROOT
from app.contracts import Pattern
from app.ingest.store import get_store
from app.miner.features import (
    cluster_intents,
    eligible,
    sequence_variance,
    split_parameters,
    window_stats,
)
from app.miner.prefixspan import SequencePattern, maximal_patterns, mine_sequences


def match_positions(sequence, pattern, max_gap=1):
    def visit(step, after, positions):
        if step == len(pattern):
            return positions
        limit = len(sequence) if step == 0 else min(len(sequence), after + max_gap + 2)
        for index in range(after + 1, limit):
            if sequence[index] == pattern[step]:
                result = visit(step + 1, index, positions + [index])
                if result is not None:
                    return result
        return None

    return visit(0, -1, [])


def score(features, thresholds, *, avg_minutes, occurrences_per_week, age_days, risk_penalty=0):
    if features["support"] < thresholds["min_support"]:
        reason = "low support"
    elif (
        features["distinct_days"] < thresholds["min_distinct_days"]
        or features["burstiness"] >= thresholds["max_burstiness"]
    ):
        reason = "one-day burst"
    elif features["variance"] >= thresholds["max_variance"]:
        reason = "high variance"
    else:
        reason = None
    confidence = (
        (1 - features["variance"])
        * (0.5 + 0.5 * features["periodicity"])
        * 2 ** (-max(0, age_days) / 14)
    )
    value = avg_minutes * occurrences_per_week * confidence - risk_penalty
    return ("declined" if reason else "mined"), reason, value


def mine_patterns(user_id, sessions, observations, policy, *, now=None, max_gap=1):
    now = now or datetime.now(timezone.utc)
    # Do not mix open episodes into recurrence counts.
    sessions = [session for session in sessions if session.status == "closed"]
    by_session = {
        session.id: eligible(
            [e for e in observations if e.session_id == session.id and e.meta.user_id == user_id]
        )
        for session in sessions
    }
    sessions = [s for s in sessions if any(e.signature != "other" for e in by_session[s.id])]
    if not sessions:
        return []
    vectors = [s.intent_embedding for s in sessions]
    labels = cluster_intents(vectors)
    output = []
    thresholds = policy["thresholds"]
    for cluster in sorted(set(labels)):
        members = [s for s, label in zip(sessions, labels) if label == cluster]
        events = [sorted(by_session[s.id], key=lambda e: e.ts) for s in members]
        sequences = [[e.signature for e in row] for row in events]
        candidates = maximal_patterns(
            mine_sequences(sequences, thresholds["min_support"], max_gap=max_gap)
        )
        # Also retain observed low-support sequences so users can inspect rejections.
        known = {item.signature for item in candidates}
        for sequence in sequences:
            signature = tuple(step for step in sequence if step != "other")[:8]
            if len(signature) < 3 or signature in known:
                continue
            support = tuple(
                i
                for i, row in enumerate(sequences)
                if match_positions(row, signature, max_gap) is not None
            )
            if len(support) < thresholds["min_support"]:
                candidates.append(SequencePattern(signature, support))
                known.add(signature)
        for candidate in candidates:
            selected = [members[i] for i in candidate.session_indexes]
            if not selected:
                continue
            matched = [
                [events[i][j] for j in match_positions(sequences[i], candidate.signature, max_gap)]
                for i in candidate.session_indexes
            ]
            full_sequences = [
                [step for step in sequences[i] if step != "other"]
                for i in candidate.session_indexes
            ]
            stats = window_stats([s.started_at for s in selected])
            stats.update(support=len(selected), variance=sequence_variance(full_sequences))
            avg_minutes = mean(s.minutes for s in selected)
            span_days = max(
                7,
                (max(s.started_at for s in selected) - min(s.started_at for s in selected)).days
                + 1,
            )
            static, dynamic = split_parameters(matched)
            risk = sum(step.startswith(("msg.send", "file.upload")) for step in candidate.signature)
            status, reason, value = score(
                stats,
                thresholds,
                avg_minutes=avg_minutes,
                occurrences_per_week=len(selected) * 7 / span_days,
                age_days=(now - max(s.ended_at for s in selected)).total_seconds() / 86400,
                risk_penalty=risk,
            )
            digest = hashlib.sha256(
                json.dumps([user_id, candidate.signature], sort_keys=True).encode()
            ).hexdigest()[:20]
            output.append(
                Pattern(
                    _id="pat_" + digest,
                    user_id=user_id,
                    status=status,
                    title=selected[0].intent_summary[:120],
                    signature=list(candidate.signature),
                    static_steps=static,
                    dynamic_params=dynamic,
                    **stats,
                    avg_minutes=avg_minutes,
                    avg_tokens=int(mean(s.tokens for s in selected)),
                    value=value,
                    evidence_session_ids=[s.id for s in selected],
                    declined_reason=reason,
                )
            )
    # The same signature can occur in unrelated intent clusters; keep the best supported result.
    unique = {}
    for pattern in output:
        if pattern.id not in unique or pattern.support > unique[pattern.id].support:
            unique[pattern.id] = pattern
    return sorted(unique.values(), key=lambda pattern: (-pattern.value, pattern.id))


async def mine_user(user_id, *, store=None, now=None):
    store = store if store is not None else get_store()
    policy = json.loads((ROOT / "fixtures/policy.json").read_text())
    policy["_id"] = f"policy:{user_id}"
    policy = await store.ensure_policy(user_id, policy)
    patterns = mine_patterns(
        user_id,
        await store.list_sessions(user_id),
        await store.observations(user_id),
        policy,
        now=now,
    )
    await store.save_patterns(user_id, patterns)
    return patterns
