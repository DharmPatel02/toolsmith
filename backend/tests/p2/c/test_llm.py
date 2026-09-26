"""P2.1.1: tiers, JSON-schema output + repair, disk cache, vision parts. LiteLLM is mocked."""
from types import SimpleNamespace

import pytest

from app import llm

SCHEMA = {"type": "object", "required": ["n"], "properties": {"n": {"type": "integer"}}}


def _resp(text, tin=10, tout=5):
    msg = SimpleNamespace(content=text, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)],
                           usage=SimpleNamespace(prompt_tokens=tin, completion_tokens=tout))


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_LEAN_MODEL", "openai/lean-x")
    monkeypatch.setenv("LLM_VISION_MODEL", "openai/vision-x")
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LLM_CACHE", raising=False)
    calls, replies = [], []

    async def acompletion(**kw):
        calls.append(kw)
        return _resp(replies.pop(0))

    monkeypatch.setattr(llm.litellm, "acompletion", acompletion)
    monkeypatch.setattr(llm, "_cost", lambda r: 0.001)
    return calls, replies


@pytest.mark.asyncio
async def test_second_identical_call_is_cached(fake):
    calls, replies = fake
    replies += ['{"n": 1}']
    msgs = [{"role": "user", "content": "give n"}]
    a = await llm.complete("lean", msgs, SCHEMA)
    b = await llm.complete("lean", msgs, SCHEMA)
    assert (a.cached, b.cached) == (False, True)
    assert b.json == {"n": 1} and b.tokens_in == 10 and b.usd == pytest.approx(0.001)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_invalid_json_is_repaired_once(fake):
    calls, replies = fake
    replies += ['{"n": "one"}', '```json\n{"n": 1}\n```']
    r = await llm.complete("lean", [{"role": "user", "content": "x"}], SCHEMA)
    assert r.json == {"n": 1} and len(calls) == 2 and r.tokens_in == 20


@pytest.mark.asyncio
async def test_invalid_json_twice_raises_and_is_not_cached(fake, tmp_path):
    _, replies = fake
    replies += ["nope", "still nope"]
    with pytest.raises(llm.LLMError):
        await llm.complete("lean", [{"role": "user", "content": "x"}], SCHEMA)
    assert not list(tmp_path.glob("*.json"))


@pytest.mark.asyncio
async def test_vision_tier_passes_image_parts(fake):
    calls, replies = fake
    replies += ['{"n": 3}']
    content = [{"type": "text", "text": "count"}, llm.image_part(b"\x00\x01", "image/png")]
    r = await llm.complete("vision", [{"role": "user", "content": content}], SCHEMA)
    assert r.json == {"n": 3} and r.model == "openai/vision-x"
    sent = calls[0]["messages"][-1]["content"][1]["image_url"]["url"]
    assert sent.startswith("data:image/png;base64,")


def test_openrouter_prefix_and_missing_model(monkeypatch):
    monkeypatch.setenv("LLM_HEAVY_MODEL", "openai/heavy-x")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    assert llm.model_for("heavy") == "openrouter/openai/heavy-x"
    monkeypatch.delenv("LLM_LEAN_MODEL", raising=False)
    with pytest.raises(llm.LLMError):
        llm.model_for("lean")


def test_parse_json_tolerates_prose():
    assert llm.parse_json('Sure! {"a": [1]} done') == {"a": [1]}
