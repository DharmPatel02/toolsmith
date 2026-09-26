"""Forge step 2 (P2.1.5): spec -> code + tests, static checks, repair <= 3."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from app import llm
from app.forge.checks import check_tests, check_tool_code
from app.prompts.forge_prompts import CODE_PROMPT, CODE_SCHEMA, REPAIR_PROMPT

MAX_REPAIRS = 3


@dataclass
class CodeResult:
    code: str
    tests: str
    problems: list[str]
    attempts: int
    usage: list[llm.LLMResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def code_prompt(spec: dict, pattern: dict, profiles: list[dict], extra: str = "") -> str:
    return ("SPEC:\n" + json.dumps(spec, indent=1)
            + "\n\nSTATIC STEPS (same every time):\n" + json.dumps(pattern.get("static_steps", {}), indent=1)
            + "\n\nOBSERVED SIGNATURE:\n" + json.dumps(pattern.get("signature", []))
            + "\n\nINPUT PROFILES FROM PAST OCCURRENCES:\n" + json.dumps(profiles, indent=1, default=str)
            + (f"\n\n{extra}" if extra else ""))


async def generate_code(spec: dict, pattern: dict, profiles: list[dict], extra: str = "") -> CodeResult:
    messages = [{"role": "system", "content": CODE_PROMPT},
                {"role": "user", "content": code_prompt(spec, pattern, profiles, extra)}]
    return await repair_loop(messages, spec)


async def repair_loop(messages: list[dict], spec: dict, max_repairs: int = MAX_REPAIRS) -> CodeResult:
    usage: list[llm.LLMResult] = []
    code = tests = ""
    problems: list[str] = []
    for attempt in range(max_repairs + 1):
        res = await llm.complete("heavy", messages, CODE_SCHEMA, max_tokens=8192)
        usage.append(res)
        code, tests = res.json["code"], res.json["tests"]
        problems = check_tool_code(code, spec.get("requires", {}).get("deps")) + check_tests(tests)
        if not problems:
            return CodeResult(code, tests, [], attempt + 1, usage)
        messages = messages + [
            {"role": "assistant", "content": res.text},
            {"role": "user", "content": REPAIR_PROMPT.format(problems="\n".join(f"- {p}" for p in problems))},
        ]
    return CodeResult(code, tests, problems, max_repairs + 1, usage)
