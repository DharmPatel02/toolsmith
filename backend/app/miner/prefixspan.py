"""Small projected-prefix miner with support by session and a max-gap constraint."""

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class SequencePattern:
    signature: tuple[str, ...]
    session_indexes: tuple[int, ...]

    @property
    def support(self):
        return len(self.session_indexes)


def mine_sequences(
    sequences: list[list[str]],
    min_support: int = 3,
    min_length: int = 3,
    max_length: int = 8,
    max_gap: int = 1,
) -> list[SequencePattern]:
    """max_gap is the maximum number of skipped steps between adjacent matches.

    Keep all possible ending positions: retaining only the first occurrence loses
    valid bounded-gap matches. Multiple occurrences in one session count once.
    """
    if min_support < 1 or min_length < 1 or max_length < min_length or max_gap < 0:
        raise ValueError("Invalid mining bounds")
    found = []

    def extend(prefix, projected):
        candidates = defaultdict(lambda: defaultdict(set))
        for sid, endings in projected.items():
            sequence = sequences[sid]
            for end in endings:
                limit = len(sequence) if not prefix else min(len(sequence), end + max_gap + 2)
                for position in range(end + 1, limit):
                    step = sequence[position]
                    if step != "other":
                        candidates[step][sid].add(position)
        for step, suffixes in sorted(candidates.items()):
            if len(suffixes) < min_support:
                continue
            signature = prefix + (step,)
            if len(signature) >= min_length:
                found.append(SequencePattern(signature, tuple(sorted(suffixes))))
            if len(signature) < max_length:
                extend(signature, suffixes)

    extend((), {index: {-1} for index in range(len(sequences))})
    return found


def maximal_patterns(patterns: list[SequencePattern]) -> list[SequencePattern]:
    """Keep the longest explanation for an identical supporting-session set."""
    kept = []
    for pattern in sorted(patterns, key=lambda p: (-len(p.signature), p.signature)):
        dominated = False
        for other in kept:
            if pattern.session_indexes != other.session_indexes:
                continue
            stream = iter(other.signature)
            if all(any(item == step for item in stream) for step in pattern.signature):
                dominated = True
                break
        if not dominated:
            kept.append(pattern)
    return kept
