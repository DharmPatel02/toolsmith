"""Embeddings (P2). Voyage text (`embed`) and multimodal image+text (`embed_multimodal`).

Store `text_model()` / `mm_model()` as `embedding_model` on every doc you embed:
one model per Atlas index, never mix.

Without VOYAGE_API_KEY this falls back to deterministic fake vectors (and says so
in the log), so the rest of the stack runs in dev and tests. Fake vectors carry
the model name "fake-<dims>" so they can't be mistaken for real ones.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os

import numpy as np

log = logging.getLogger(__name__)

TEXT_BATCH = 128
MM_BATCH = 32
_client = None
_warned = False


def _dims() -> int:
    return int(os.getenv("EMBED_DIMS", "1024"))


def _fake() -> bool:
    global _warned
    fake = not os.getenv("VOYAGE_API_KEY")
    if fake and not _warned:
        log.warning("VOYAGE_API_KEY not set: using FAKE embeddings (dev only)")
        _warned = True
    return fake


def text_model() -> str:
    return f"fake-{_dims()}" if _fake() else os.getenv("EMBED_MODEL", "voyage-3.5")


def mm_model() -> str:
    if _fake():
        return f"fake-{_dims()}"
    model = os.getenv("VOYAGE_MM_MODEL")
    if not model:
        raise RuntimeError("VOYAGE_MM_MODEL is not set (see .env.example)")
    return model


def _voyage():
    global _client
    if _client is None:
        import voyageai

        _client = voyageai.AsyncClient(api_key=os.environ["VOYAGE_API_KEY"], max_retries=3)
    return _client


async def embed(texts: list[str], input_type: str = "document") -> list[list[float]]:
    """Embed texts (input_type "document" for stored docs, "query" for searches)."""
    if not texts:
        return []
    if _fake():
        return [_fake_vec(t) for t in texts]
    out: list[list[float]] = []
    for i in range(0, len(texts), TEXT_BATCH):
        res = await _voyage().embed(texts[i:i + TEXT_BATCH], model=text_model(), input_type=input_type)
        out.extend(res.embeddings)
    return out


async def embed_multimodal(items: list[dict]) -> list[list[float]]:
    """Embed frames. item = {"image_bytes": bytes, "text": str}; either may be missing."""
    if not items:
        return []
    if _fake():
        return [_fake_vec((it.get("text") or "") + hashlib.sha256(it.get("image_bytes") or b"").hexdigest())
                for it in items]
    from PIL import Image

    inputs = []
    for it in items:
        parts: list = []
        if it.get("text"):
            parts.append(it["text"])
        if it.get("image_bytes"):
            parts.append(Image.open(io.BytesIO(it["image_bytes"])).convert("RGB"))
        if not parts:
            raise ValueError("embed_multimodal item needs image_bytes or text")
        inputs.append(parts)
    out: list[list[float]] = []
    for i in range(0, len(inputs), MM_BATCH):
        res = await _voyage().multimodal_embed(inputs[i:i + MM_BATCH], model=mm_model(), input_type="document")
        out.extend(res.embeddings)
    return out


def cosine(a: list[float], b: list[float]) -> float:
    va, vb = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(va @ vb / denom) if denom else 0.0


def _fake_vec(text: str) -> list[float]:
    seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "little")
    v = np.random.default_rng(seed).standard_normal(_dims())
    return (v / np.linalg.norm(v)).tolist()
