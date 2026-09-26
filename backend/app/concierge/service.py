"""Concierge (P2.3.6, P1 priority): POST /chat -> lean tool-calling loop with recall_episodes,
search_tools and run_tool (dry run only). Conversations persist in `conversations`.

ChatReply = {conversation_id, reply, tool_calls, cards}; cards are what the UI can render next to
the answer: {"type": "episodes"|"tools"|"run", "items"|...}.
"""
from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from typing import Any

from app import llm
from app.forge import deps
from app.prompts.concierge_prompts import CONCIERGE_PROMPT, CONCIERGE_TOOLS

MAX_ROUNDS = 5
HISTORY = 20


async def chat(user_id: str, conversation_id: str | None, message: str) -> dict:
    db = deps.get_db()
    conv = await db.conversations.find_one({"_id": conversation_id, "user_id": user_id}) if conversation_id else None
    conversation_id = (conv or {}).get("_id") or "conv_" + secrets.token_hex(4)
    history = [{"role": m["role"], "content": m["content"]} for m in (conv or {}).get("messages", [])][-HISTORY:]
    messages = [{"role": "system", "content": CONCIERGE_PROMPT}, *history, {"role": "user", "content": message}]

    calls, cards = [], []
    reply = ""
    usage = {"tokens": 0, "usd": 0.0}
    for _ in range(MAX_ROUNDS):
        res = await llm.complete("lean", messages, tools=CONCIERGE_TOOLS, max_tokens=1024)
        usage["tokens"] += res.tokens_in + res.tokens_out
        usage["usd"] += res.usd
        if not res.tool_calls:
            reply = res.text.strip()
            break
        messages.append({"role": "assistant", "content": res.text or None, "tool_calls": [
            {"id": tc["id"], "type": "function", "function": {"name": tc["name"],
                                                              "arguments": json.dumps(tc["arguments"])}}
            for tc in res.tool_calls]})
        for tc in res.tool_calls:
            args = tc["arguments"] if isinstance(tc["arguments"], dict) else {}
            result, card = await _call(user_id, tc["name"], args)
            calls.append({"name": tc["name"], "arguments": args})
            if card:
                cards.append(card)
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(result, default=str)[:4000]})
    else:
        reply = reply or "I couldn't finish that in a few steps. Try asking more narrowly."

    now = datetime.now(UTC)
    await db.conversations.update_one(
        {"_id": conversation_id},
        {"$setOnInsert": {"user_id": user_id, "created_at": now},
         "$push": {"messages": {"$each": [{"role": "user", "content": message, "ts": now},
                                          {"role": "assistant", "content": reply, "ts": now, "tool_calls": calls}]}},
         "$set": {"updated_at": now}, "$inc": {"tokens": usage["tokens"]}},
        upsert=True)
    return {"conversation_id": conversation_id, "reply": reply, "tool_calls": calls, "cards": cards}


async def _call(user_id: str, name: str, args: dict) -> tuple[Any, dict | None]:
    if name == "recall_episodes":
        hits = [_plain(h) for h in await deps.recall_episodes(user_id, args.get("query", ""), 5)]
        return hits, {"type": "episodes", "items": hits}
    if name == "search_tools":
        hits = [_plain(h) for h in await deps.search_tools(user_id, args.get("query", ""), 5)]
        return hits, {"type": "tools", "items": hits}
    if name == "run_tool":
        tool_id = args.get("tool_id", "")
        try:
            res = _plain(await deps.run_tool(user_id, tool_id, args.get("params") or {}, False))
        except ImportError:
            return {"error": "the runtime is not available yet"}, None
        except Exception as e:  # noqa: BLE001 - tell the model, don't crash the chat
            return {"error": str(e)[:300]}, None
        return res, {"type": "run", "tool_id": tool_id, "result": res}
    return {"error": f"unknown function {name}"}, None


def _plain(x: Any) -> Any:
    if hasattr(x, "model_dump"):
        return x.model_dump(mode="json")
    if hasattr(x, "__dataclass_fields__"):
        from dataclasses import asdict

        return asdict(x)
    return x
