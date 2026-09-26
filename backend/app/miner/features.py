"""Measurable repetition features; no workflow labels or ground truth are read."""

from collections import Counter
from difflib import SequenceMatcher
from itertools import combinations
from statistics import median

import numpy as np
from sklearn.cluster import AgglomerativeClustering


def cluster_intents(vectors: list[list[float]], similarity: float = 0.8) -> list[int]:
    if not vectors:
        return []
    values = np.asarray(vectors, dtype=float)
    if (
        values.ndim != 2
        or not np.isfinite(values).all()
        or (np.linalg.norm(values, axis=1) == 0).any()
    ):
        raise ValueError("Intent vectors must be finite, nonzero, and share a dimension")
    if len(values) == 1:
        return [0]
    return (
        AgglomerativeClustering(
            n_clusters=None, metric="cosine", linkage="average", distance_threshold=1 - similarity
        )
        .fit_predict(values)
        .tolist()
    )


def eligible(events):
    return [e for e in events if not e.evidence.needs_review and e.evidence.confidence >= 0.6]


def window_stats(times):
    ordered = sorted(times)
    if not ordered:
        return {"distinct_days": 0, "periodicity": 0.0, "burstiness": 0.0}
    days = Counter(ts.date() for ts in ordered)
    intervals = [(b - a).total_seconds() for a, b in zip(ordered, ordered[1:])]
    typical = median(intervals) if intervals else 0
    deviation = median(abs(gap - typical) for gap in intervals) if intervals else 0
    periodicity = max(0.0, 1 - deviation / typical) if typical > 0 and len(intervals) >= 2 else 0.0
    return {
        "distinct_days": len(days),
        "periodicity": periodicity,
        "burstiness": max(days.values()) / len(ordered),
    }


def sequence_variance(sequences):
    similarities = [
        SequenceMatcher(None, a, b, autojunk=False).ratio() for a, b in combinations(sequences, 2)
    ]
    return 1 - median(similarities) if similarities else 0.0


def split_parameters(occurrences):
    """Compare values at corresponding action positions, preserving repeated actions."""
    static, dynamic = {}, []
    width = max((len(events) for events in occurrences), default=0)
    for index in range(width):
        available = [events[index] for events in occurrences if index < len(events)]
        shapes = [
            {
                **event.args_shape,
                **{
                    f"element.{key}": event.target[key]
                    for key in ("role", "name")
                    if key in event.target
                },
            }
            for event in available
        ]
        fields = set().union(*(shape.keys() for shape in shapes))
        for field in sorted(fields):
            values = [shape.get(field) for shape in shapes]
            name = f"step_{index}.{field}"
            if len(available) == len(occurrences) and all(value == values[0] for value in values):
                static[name] = values[0]
            else:
                kind = "file" if field in ("file", "path") else "string"
                dynamic.append({"name": name, "type": kind})
    return static, dynamic
