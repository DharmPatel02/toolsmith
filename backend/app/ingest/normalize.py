"""Redact before storage or model input; signatures contain shapes, not raw values."""

import hashlib
import json
import re

from app.contracts import Observation
from app.miner.signatures import to_signature

_SECRET_KEY = re.compile(r"(?:password|passwd|secret|token|api[_-]?key|authorization)", re.I)
_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]+", re.I),
    re.compile(r"\b(?:password|token|api[_-]?key|secret)\s*[:=]\s*[\"\']?[^\s,;\"\']+", re.I),
]


def redact(value):
    if isinstance(value, dict):
        return {
            key: "<REDACTED>" if _SECRET_KEY.search(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        for pattern in _PATTERNS:
            value = pattern.sub("<REDACTED>", value)
    return value


def normalize(event: Observation) -> Observation:
    # Preserve routing identifiers/timestamps while redacting all content-bearing fields.
    content = redact(
        {
            key: getattr(event, key)
            for key in ("target", "args_shape", "intent_text", "error", "artifacts")
        }
    )
    evidence = event.evidence.model_dump()
    evidence["ocr_snippet"] = redact(evidence["ocr_snippet"])
    evidence["needs_review"] |= evidence["confidence"] < 0.6
    signature = to_signature(event.action, content["args_shape"])
    if signature == "other" and event.signature:
        signature = to_signature(event.signature, content["args_shape"])
    content.update(
        signature=signature,
        action=signature.split(":")[0],
        evidence=evidence,
        params_hash=hashlib.sha256(
            json.dumps(content["args_shape"], sort_keys=True).encode()
        ).hexdigest(),
    )
    return Observation.model_validate({**event.model_dump(), **content})
