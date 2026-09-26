"""P2.1.10: 3 strings -> 3 vectors; 1 image + text -> 1 multimodal vector.
Unit tests use the fake path; the live test runs once VOYAGE_API_KEY is set."""
import io
import os

import pytest
from dotenv import load_dotenv
from PIL import Image

from app import embeddings as emb

load_dotenv()
REAL_KEY = os.getenv("VOYAGE_API_KEY")


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (0, 128, 0)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)


@pytest.mark.asyncio
async def test_fake_text_vectors(no_key):
    v = await emb.embed(["a", "b", "a"])
    assert len(v) == 3 and len(v[0]) == 1024
    assert v[0] == v[2] and emb.cosine(v[0], v[1]) < 0.2
    assert emb.text_model() == "fake-1024"


@pytest.mark.asyncio
async def test_fake_multimodal_vector(no_key):
    v = await emb.embed_multimodal([{"image_bytes": _png(), "text": "pivot table"}])
    assert len(v) == 1 and len(v[0]) == 1024


@pytest.mark.asyncio
async def test_batches_of_128(monkeypatch):
    monkeypatch.setenv("VOYAGE_API_KEY", "k")
    sizes = []

    class FakeClient:
        async def embed(self, texts, model, input_type):
            sizes.append(len(texts))
            return type("R", (), {"embeddings": [[0.0]] * len(texts)})

    monkeypatch.setattr(emb, "_client", FakeClient())
    out = await emb.embed([str(i) for i in range(300)])
    assert len(out) == 300 and sizes == [128, 128, 44]


@pytest.mark.skipif(not REAL_KEY, reason="no VOYAGE_API_KEY in .env")
@pytest.mark.asyncio
async def test_live_voyage(monkeypatch):
    monkeypatch.setattr(emb, "_client", None)
    t = await emb.embed(["weekly sales dashboard", "monday pivot report", "cat pictures"])
    assert len(t) == 3
    assert emb.cosine(t[0], t[1]) > emb.cosine(t[0], t[2])
    if os.getenv("VOYAGE_MM_MODEL"):
        m = await emb.embed_multimodal([{"image_bytes": _png(), "text": "excel pivot"}])
        assert len(m) == 1 and len(m[0]) > 0
