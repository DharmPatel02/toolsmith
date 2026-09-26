"""Forge step 3 (P2.1.6): TOOL.md, <= 350 words, the 5 fixed headings."""
from __future__ import annotations

import json
import re

from app import llm
from app.prompts.forge_prompts import TUTORIAL_HEADINGS, TUTORIAL_PROMPT

MAX_WORDS = 350


def word_count(md: str) -> int:
    return len(re.findall(r"[A-Za-z0-9][\w'.,%/-]*", md))


def tutorial_problems(md: str) -> list[str]:
    problems = []
    heads = [h.strip() for h in re.findall(r"^##\s+(.+)$", md, flags=re.MULTILINE)]
    if heads != TUTORIAL_HEADINGS:
        problems.append(f"headings must be exactly {TUTORIAL_HEADINGS}, got {heads}")
    if (n := word_count(md)) > MAX_WORDS:
        problems.append(f"{n} words, max {MAX_WORDS}")
    if "```" in md:
        problems.append("no code blocks")
    return problems


async def write_tutorial(spec: dict, example: dict | None) -> tuple[str, list[llm.LLMResult]]:
    user = ("SPEC:\n" + json.dumps({k: spec.get(k) for k in ("name", "title", "purpose", "params_schema",
                                                               "outputs", "steps", "derivation")}, indent=1)
            + "\n\nEXAMPLE RUN:\n" + json.dumps(example or {}, indent=1, default=str))
    messages = [{"role": "system", "content": TUTORIAL_PROMPT}, {"role": "user", "content": user}]
    usage = []
    for _ in range(2):
        res = await llm.complete("lean", messages, max_tokens=1200)
        usage.append(res)
        md = res.text.strip()
        problems = tutorial_problems(md)
        if not problems:
            return md, usage
        messages = messages + [{"role": "assistant", "content": res.text},
                               {"role": "user", "content": "Fix: " + "; ".join(problems)}]
    return fallback_tutorial(spec, example), usage


def fallback_tutorial(spec: dict, example: dict | None) -> str:
    """Deterministic TOOL.md so a candidate never ships without one."""
    props = spec.get("params_schema", {}).get("properties", {})
    params = "\n".join(f"- **{n}**: {'a file' if p.get('format') == 'file' else p.get('type', 'value')}"
                       + (f" ({p['description']})" if p.get("description") else "") for n, p in props.items())
    outs = spec.get("outputs", {})
    got = ", ".join([*(f"table {t}" for t in outs.get("tables", [])),
                     *(["a chart"] if outs.get("chart") else []), *outs.get("files", [])]) or "a summary"
    ex = ", ".join(f"{k} = {v}" for k, v in ((example or {}).get("inputs") or {}).items()) or "see the run panel"
    steps = "; ".join(spec.get("steps", []))
    return (f"# {spec.get('title', spec.get('name', 'Tool'))}\n\n"
            f"## What it does\n{spec.get('purpose', '')} Steps: {steps}.\n\n"
            f"## What you give it\n{params}\n\n"
            f"## What you get back\n{got}.\n\n"
            f"## Example\nRun it with {ex}.\n\n"
            f"## Limits\nOnly handles inputs shaped like the ones it was built from; "
            f"anything else stops with a clear error instead of guessing.\n")
