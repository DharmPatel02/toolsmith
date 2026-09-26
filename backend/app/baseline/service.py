"""Race (P2.3.3): the baseline agent vs the toolbox, side by side, both streaming `race_step`.

- baseline: lean model, no tools of its own, solves the task from scratch (inspect -> code ->
  run -> fix -> finish); every model call is one step.
- tool: `run_by_intent` (P1 runtime): find the saved tool, run it at its trust level. Until
  P1's runtime is merged, a local fallback searches the toolbox and runs the tool dry.

`race_step.data = {race_id, side, step, label, tokens, elapsed_ms, done}` (TASKS §3.4).
Results land in `races` for the metrics page.
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path

from app import llm
from app.forge import deps
from app.forge.checks import check_tool_code
from app.forge.spec import input_names, profile_inputs, resolve_artifact
from app.prompts.baseline_prompts import BASELINE_PROMPT, BASELINE_TOOLS
from app.sandbox import run_in_sandbox

log = logging.getLogger(__name__)
MAX_STEPS = 15
TOOL_RESULT_CHARS = 2500


def new_race_id() -> str:
    return "race_" + secrets.token_hex(4)


class _Clock:
    def __init__(self, user_id: str, race_id: str, side: str):
        self.user_id, self.race_id, self.side = user_id, race_id, side
        self.t0 = time.monotonic()
        self.step = 0
        self.tokens = 0

    def ms(self) -> int:
        return int((time.monotonic() - self.t0) * 1000)

    async def emit(self, label: str, done: bool = False, **extra) -> None:
        self.step += 1
        await deps.publish(self.user_id, "race_step", {
            "race_id": self.race_id, "side": self.side, "step": self.step, "label": label,
            "tokens": self.tokens, "elapsed_ms": self.ms(), "done": done, **extra})


# ---- baseline ------------------------------------------------------------------

async def run_baseline(user_id: str, intent: str, inputs: dict, race_id: str) -> dict:
    clock = _Clock(user_id, race_id, "baseline")
    files = {k: str(resolve_artifact(v)) for k, v in inputs.items() if _is_file(v)}
    values = {k: v for k, v in inputs.items() if k not in files}
    messages = [{"role": "system", "content": BASELINE_PROMPT},
                {"role": "user", "content": f"{intent}\n\nInputs: {json.dumps(sorted(files))}"
                                            + (f"\nValues: {json.dumps(values)}" if values else "")}]
    usd, summary, error, last_output = 0.0, None, None, None
    try:
        while clock.step < MAX_STEPS:
            res = await llm.complete("lean", messages, tools=BASELINE_TOOLS, max_tokens=2048)
            clock.tokens += res.tokens_in + res.tokens_out
            usd += res.usd
            if not res.tool_calls:  # answered in plain text
                summary = res.text.strip() or "(no answer)"
                await clock.emit("answer", done=True)
                break
            messages.append({"role": "assistant", "content": res.text or None, "tool_calls": [
                {"id": tc["id"], "type": "function",
                 "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])}}
                for tc in res.tool_calls]})
            labels = []
            for tc in res.tool_calls:
                args = tc["arguments"] if isinstance(tc["arguments"], dict) else {}
                if tc["name"] == "finish":
                    summary = args.get("summary") or ""
                    content = "ok"
                    labels.append("finish")
                else:
                    content, label, out = await _baseline_tool(tc["name"], args, files)
                    last_output = out or last_output
                    labels.append(label)
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": content[:TOOL_RESULT_CHARS]})
            done = summary is not None
            await clock.emit(" · ".join(labels), done=done)
            if done:
                break
        else:
            error = f"gave up after {MAX_STEPS} steps"
            await clock.emit("gave up", done=True)
    except llm.LLMError as e:
        error = str(e)
        await clock.emit("model error", done=True, error=error[:200])
    return {"race_id": race_id, "side": "baseline", "ok": summary is not None and error is None,
            "steps": clock.step, "tokens": clock.tokens, "usd": round(usd, 6), "elapsed_ms": clock.ms(),
            "seconds": round(clock.ms() / 1000, 1), "summary": summary, "error": error, "output": last_output}


async def _baseline_tool(name: str, args: dict, files: dict[str, str]) -> tuple[str, str, dict | None]:
    if name == "list_inputs":
        profiles = profile_inputs(list(files.values()))
        by_file = {Path(p).name: n for n, p in files.items()}
        return json.dumps([{"name": by_file.get(p["file"], p["file"]), "rows": p["rows"], "columns": p["columns"],
                            "dtypes": p["dtypes"]} for p in profiles]), "list inputs", None
    if name == "preview_table":
        import pandas as pd

        path = files.get(args.get("name", ""))
        if not path:
            return f"no input named {args.get('name')!r}; inputs: {sorted(files)}", "preview (bad name)", None
        df = pd.read_excel(path) if path.endswith((".xlsx", ".xls")) else pd.read_csv(path)
        return df.head(min(int(args.get("rows") or 5), 20)).to_csv(index=False), f"preview {args['name']}", None
    if name == "run_python":
        code = args.get("code") or ""
        problems = check_tool_code(code)
        if problems:
            return "REJECTED:\n" + "\n".join(problems), "run python (rejected)", None
        r = await run_in_sandbox(code, "run", {}, files, "dry_run", [], timeout_s=60)
        if not r.ok:
            last = (r.error or "").strip().splitlines()[-1:] or ["error"]
            return "ERROR:\n" + (r.error or "")[-1500:], f"run python → {last[0][:60]}", None
        return ("OK. Result:\n" + json.dumps(r.output, default=str)[:TOOL_RESULT_CHARS - 200]
                + "\n\nIf this answers the request, call finish now with a one-line summary."), "run python ✓", r.output
    return f"unknown function {name}", f"unknown {name}", None


def _is_file(v) -> bool:
    return isinstance(v, str) and len(v) < 400 and resolve_artifact(v).is_file()


# ---- tool side ------------------------------------------------------------------

async def run_tool_side(user_id: str, intent: str, inputs: dict, race_id: str) -> dict:
    clock = _Clock(user_id, race_id, "tool")
    await clock.emit("search toolbox")
    try:
        try:
            res = await deps.run_by_intent(user_id, intent, inputs)
        except ImportError:
            res = await _local_run_by_intent(user_id, intent, inputs)
        route, tool_id = deps.field(res, "route"), deps.field(res, "tool_id")
        clock.tokens = int(deps.field(res, "tokens", 0) or 0)
        output = deps.field(res, "output") or {}
        ok = route == "found" and not deps.field(res, "error")
        label = f"run {deps.field(res, 'name') or tool_id} ({deps.field(res, 'mode') or 'dry_run'})" if tool_id \
            else f"no tool ({route})"
        await clock.emit(label, done=True, route=route, tool_id=tool_id)
        return {"race_id": race_id, "side": "tool", "ok": ok, "route": route, "tool_id": tool_id,
                "steps": clock.step, "tokens": clock.tokens, "usd": 0.0, "elapsed_ms": clock.ms(),
                "seconds": round(clock.ms() / 1000, 1), "summary": output.get("summary"), "output": output,
                "error": deps.field(res, "error")}
    except Exception as e:  # noqa: BLE001 - the race view must always get a final step
        log.exception("tool side of %s failed", race_id)
        await clock.emit("error", done=True, error=str(e)[:200])
        return {"race_id": race_id, "side": "tool", "ok": False, "steps": clock.step, "tokens": clock.tokens,
                "elapsed_ms": clock.ms(), "seconds": round(clock.ms() / 1000, 1), "error": str(e)}


async def _local_run_by_intent(user_id: str, intent: str, inputs: dict) -> dict:
    """Dev fallback for P1's runtime: top toolbox hit above T_low -> run its active version dry."""
    db = deps.get_db()
    hits = await deps.search_tools(user_id, intent, 3)
    if not hits:
        return {"route": "not_found", "tool_id": None, "tokens": 0}
    top = hits[0] if isinstance(hits[0], dict) else {"tool_id": deps.field(hits[0], "tool_id"),
                                                      "score": deps.field(hits[0], "score")}
    tool = await db.tools.find_one({"_id": top["tool_id"]})
    tv = await db.tool_versions.find_one({"_id": f"{tool['_id']}@v{tool['active_version']}"})
    files = set(input_names({"params_schema": tv["params_schema"]}))
    params = {k: (k if k in files else v) for k, v in inputs.items()}  # file params = input handles
    r = await run_in_sandbox(tv["code"], "run", params,
                             {k: str(resolve_artifact(v)) for k, v in inputs.items() if k in files}, "dry_run",
                             tv["requires"].get("scopes", []), timeout_s=60)
    return {"route": "found", "tool_id": tool["_id"], "name": tool.get("name"), "score": top.get("score"),
            "mode": "dry_run", "output": r.output, "tokens": 0, "duration_ms": r.duration_ms,
            "error": None if r.ok else r.error}


# ---- race -------------------------------------------------------------------------

async def start_race(user_id: str, intent: str, inputs: dict, race_id: str | None = None) -> str:
    race_id = race_id or new_race_id()
    await deps.get_db().races.insert_one({"_id": race_id, "user_id": user_id, "intent": intent, "inputs": inputs,
                                          "status": "running", "started_at": datetime.now(UTC)})
    return race_id


async def run_race(user_id: str, intent: str, inputs: dict, race_id: str) -> dict:
    baseline, tool = await asyncio.gather(run_baseline(user_id, intent, inputs, race_id),
                                          run_tool_side(user_id, intent, inputs, race_id))
    summary = {side: {k: r.get(k) for k in ("ok", "steps", "seconds", "tokens", "usd")}
               for side, r in (("baseline", baseline), ("tool", tool))}
    await deps.get_db().races.update_one({"_id": race_id}, {"$set": {
        "status": "done", "baseline": _slim(baseline), "tool": _slim(tool), "summary": summary,
        "finished_at": datetime.now(UTC)}})
    return {"race_id": race_id, **summary}


def _slim(r: dict) -> dict:
    return {k: v for k, v in r.items() if k != "output"}
