"""P2.1.1 live check against the real provider. Skipped until keys + models are in .env."""
import io
import os

import pytest
from dotenv import load_dotenv
from PIL import Image

from app import llm

load_dotenv()
live = pytest.mark.skipif(
    not (os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")) or not os.getenv("LLM_VISION_MODEL"),
    reason="no LLM key / LLM_VISION_MODEL in .env",
)
SCHEMA = {"type": "object", "required": ["color"], "properties": {"color": {"type": "string"}}}


@live
@pytest.mark.asyncio
async def test_vision_call_returns_valid_json(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (220, 20, 20)).save(buf, "WEBP")
    content = [{"type": "text", "text": "What is the dominant color? JSON {\"color\": ...}"},
               llm.image_part(buf.getvalue())]
    a = await llm.complete("vision", [{"role": "user", "content": content}], SCHEMA)
    assert "red" in a.json["color"].lower() and a.tokens_in > 0
    b = await llm.complete("vision", [{"role": "user", "content": content}], SCHEMA)
    assert b.cached
