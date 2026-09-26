"""LLM client (P2). One entry point, `complete`, over LiteLLM.

Tiers map to env models: lean -> LLM_LEAN_MODEL, heavy -> LLM_HEAVY_MODEL,
vision -> LLM_VISION_MODEL (accepts image content parts, see `image_part`).
If OPENROUTER_API_KEY is set, every call is routed through OpenRouter.

Identical calls are served from a disk cache (LLM_CACHE_DIR) so the demo is
deterministic and cheap. Set LLM_CACHE=off to bypass it.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import jsonschema
import litellm

log = logging.getLogger(__name__)
litellm.suppress_debug_info = True

Tier = Literal["lean", "heavy", "vision"]
_TIER_ENV = {"lean": "LLM_LEAN_MODEL", "heavy": "LLM_HEAVY_MODEL", "vision": "LLM_VISION_MODEL"}
_JSON_REPAIR_ATTEMPTS = 1


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    json: Any = None
    tokens_in: int = 0
    tokens_out: int = 0
    usd: float = 0.0
    model: str = ""
    cached: bool = False
    tool_calls: list[dict] = field(default_factory=list)  # only when `tools` was passed


def image_part(data: bytes, mime: str = "image/webp") -> dict:
    """OpenAI-style image content part for the vision tier."""
    b64 = base64.b64encode(data).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def model_for(tier: Tier) -> str:
    env = _TIER_ENV[tier]
    model = os.getenv(env)
    if not model:
        raise LLMError(f"{env} is not set (see .env.example)")
    if os.getenv("OPENROUTER_API_KEY") and not model.startswith("openrouter/"):
        model = f"openrouter/{model}"
    return model


async def complete(
    tier: Tier,
    messages: list[dict],
    json_schema: dict | None = None,
    *,
    tools: list[dict] | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    cache: bool = True,
) -> LLMResult:
    """Run one chat completion. With `json_schema`, the reply is parsed and
    validated into `.json` (one repair round-trip if it doesn't validate)."""
    model = model_for(tier)
    use_cache = cache and os.getenv("LLM_CACHE", "on").lower() != "off"
    key = _cache_key(model, messages, json_schema, tools, temperature)
    if use_cache and (hit := _cache_get(key)):
        return hit

    msgs = list(messages)
    total_in = total_out = 0
    usd = 0.0
    for attempt in range(_JSON_REPAIR_ATTEMPTS + 1):
        resp = await _call(model, msgs, json_schema, tools, temperature, max_tokens)
        choice = resp.choices[0].message
        text = choice.content or ""
        total_in += getattr(resp.usage, "prompt_tokens", 0) or 0
        total_out += getattr(resp.usage, "completion_tokens", 0) or 0
        usd += _cost(resp)
        tool_calls = [
            {"id": tc.id, "name": tc.function.name, "arguments": _loads_or_raw(tc.function.arguments)}
            for tc in (getattr(choice, "tool_calls", None) or [])
        ]
        result = LLMResult(text=text, tokens_in=total_in, tokens_out=total_out, usd=usd,
                           model=model, tool_calls=tool_calls)
        if json_schema is None or tool_calls:
            break
        try:
            result.json = parse_json(text)
            jsonschema.validate(result.json, json_schema)
            break
        except (ValueError, jsonschema.ValidationError) as e:
            err = e.message if isinstance(e, jsonschema.ValidationError) else str(e)
            if attempt == _JSON_REPAIR_ATTEMPTS:
                raise LLMError(f"{model} returned invalid JSON after repair: {err}") from e
            log.warning("llm json invalid (%s), asking for a repair", err)
            msgs = msgs + [
                {"role": "assistant", "content": text},
                {"role": "user", "content": f"That JSON is invalid: {err}. Reply with corrected JSON only."},
            ]

    if use_cache:
        _cache_put(key, result)
    return result


async def _call(model, messages, json_schema, tools, temperature, max_tokens):
    kwargs: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature,
                              "max_tokens": max_tokens, "num_retries": 2, "timeout": 120}
    if tools:
        kwargs["tools"] = tools
    elif json_schema is not None:
        if _supports_schema(model):
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": json_schema, "strict": False},
            }
        else:
            kwargs["messages"] = [
                {"role": "system", "content": "Reply with JSON only, matching this JSON schema:\n"
                 + json.dumps(json_schema)},
                *messages,
            ]
    try:
        return await litellm.acompletion(**kwargs)
    except Exception as e:  # surface one clear error type to callers
        raise LLMError(f"{model}: {e}") from e


def _supports_schema(model: str) -> bool:
    try:
        return bool(litellm.supports_response_schema(model=model))
    except Exception:  # noqa: BLE001 - unknown model in litellm's map
        return False


def _cost(resp) -> float:
    try:
        return float(litellm.completion_cost(completion_response=resp) or 0.0)
    except Exception:  # noqa: BLE001 - model missing from the price map
        return 0.0


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json(text: str) -> Any:
    """Parse model output as JSON, tolerating ``` fences and leading prose."""
    s = _FENCE.sub("", text.strip()).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        start = min((i for i in (s.find("{"), s.find("[")) if i >= 0), default=-1)
        if start < 0:
            raise ValueError("no JSON object in reply") from None
        obj, _ = json.JSONDecoder().raw_decode(s[start:])
        return obj


def _loads_or_raw(s: str) -> Any:
    try:
        return json.loads(s)
    except (TypeError, json.JSONDecodeError):
        return s


# ---- disk cache ----------------------------------------------------------

def _cache_dir() -> Path:
    return Path(os.getenv("LLM_CACHE_DIR", ".cache/llm"))


def _cache_key(model, messages, json_schema, tools, temperature) -> str:
    blob = json.dumps([model, messages, json_schema, tools, temperature], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def _cache_get(key: str) -> LLMResult | None:
    path = _cache_dir() / f"{key}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    data["cached"] = True
    return LLMResult(**data)


def _cache_put(key: str, result: LLMResult) -> None:
    d = _cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{key}.tmp"
    tmp.write_text(json.dumps(asdict(result)), encoding="utf-8")
    tmp.replace(d / f"{key}.json")
