"""Forge prompts + JSON schemas (P2.1.4-P2.1.6): spec, code + tests, tutorial."""
from __future__ import annotations

from app.forge.checks import ALLOWED_IMPORTS
from app.gate.testkit import FAKE_CTX_API

# ---- spec -----------------------------------------------------------------

SPEC_PROMPT = """\
You design a small, reusable tool from a workflow a user repeats. You get the mined pattern
(canonical step signature, static steps, dynamic params, how it was observed) and profiles of
the real input files from past occurrences.

Return a ToolSpec as JSON:
- name: snake_case, 3-40 chars, describes the job (e.g. "weekly_sales_rollup").
- title: short human title. purpose: one sentence, plain language.
- params_schema: JSON schema {"type":"object","properties":{...},"required":[...]}. One property per
  dynamic param. A param whose type is file gets {"type":"string","format":"file"}: it is an INPUT the
  tool reads with ctx.read_table(<param name>), not a value.
- outputs: {"tables": [names], "chart": true|false, "files": [file names written, e.g. "dashboard.html"]}.
- requires: {"scopes": [...], "deps": [...], "tools": []}. Scopes: "write:outputs" if it writes files,
  "net:<domain>" per domain it fetches, "app:<app>" per app it asks to act in (slack, jira, tracker,
  email). deps only from: pandas, numpy, openpyxl, bs4, lxml, plotly.
- keywords: 5-10 search words a user might type to find this tool.
- steps: the tool's steps in plain words, in order.
- derivation: {"observed_tier": "T0|T1|T2", "execution_path": "api|browser|cli|assisted"}.
  observed_tier = how the workflow was SEEN (T0 logs, T1 browser UI events, T2 screen pixels).
  execution_path = how the tool will RUN. **Prefer "api"**: a workflow seen in Excel on screen still
  runs as pandas + openpyxl. Only use "assisted" if no programmatic path exists.
- not_automatable: null, or {"reason": ...} if the workflow is destructive, needs human judgement,
  or can't be verified. Then code will not be generated.
"""

SPEC_SCHEMA: dict = {
    "type": "object",
    "required": ["name", "title", "purpose", "params_schema", "outputs", "requires", "keywords",
                 "steps", "derivation"],
    "properties": {
        "name": {"type": "string", "pattern": "^[a-z][a-z0-9_]{2,40}$"},
        "title": {"type": "string"},
        "purpose": {"type": "string"},
        "params_schema": {"type": "object", "required": ["type", "properties"],
                          "properties": {"type": {"const": "object"}, "properties": {"type": "object"},
                                         "required": {"type": "array", "items": {"type": "string"}}}},
        "outputs": {"type": "object"},
        "requires": {"type": "object", "required": ["scopes", "deps"],
                     "properties": {"scopes": {"type": "array", "items": {"type": "string"}},
                                    "deps": {"type": "array", "items": {"type": "string"}},
                                    "tools": {"type": "array", "items": {"type": "string"}}}},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "steps": {"type": "array", "items": {"type": "string"}},
        "derivation": {"type": "object", "required": ["observed_tier", "execution_path"],
                       "properties": {"observed_tier": {"enum": ["T0", "T1", "T2"]},
                                      "execution_path": {"enum": ["api", "browser", "cli", "assisted"]}}},
        "not_automatable": {"type": ["object", "null"]},
    },
}

# ---- code + tests ---------------------------------------------------------

CODE_PROMPT = f"""\
You write the Python code for a tool from its spec. Output JSON {{"code": "...", "tests": "..."}}.

CODE contract:
- A module with a top-level `def run(ctx, **params) -> dict`. Helpers are fine.
- Read inputs ONLY through ctx: `ctx.read_table(name)` -> pandas DataFrame (xlsx/csv),
  `ctx.read_text(name)`, `ctx.fetch(url)` (needs scope "net:<domain>"). No open(), no os, no files.
- File params (format "file") are mounted inputs: their value is the input's name, so
  `ctx.read_table(params["file"])` and `ctx.read_table("file")` are the same. Other params
  (e.g. week) arrive as plain values in `params`. Never open paths yourself.
- Write files ONLY with `ctx.write_output(name, content_str)`.
- Effects in other apps are REQUESTED, never performed: `ctx.action("slack.post", channel=..., text=...)`,
  `ctx.action("jira.create", summary=..., description=...)`, `ctx.action("tracker.upsert", ref=...,
  status=..., note=...)` (needs scope "app:<app>"). The runtime does them after the user or an approver
  confirms. Never call HTTP APIs, SDKs or webhooks yourself.
- If spec.requires.tools names existing tools, reuse them with `ctx.call("<tool>", **params)` (returns
  that tool's result dict) instead of re-implementing them.
- Allowed imports: {", ".join(sorted(ALLOWED_IMPORTS))}. Nothing else.
- Return {{"summary": str, "tables": {{name: list of row dicts}}, "chart_spec": {{"type": "bar|line",
  "x": [...], "y": [...], "title": str}}}} (omit chart_spec if there is no chart).
  Sort table rows by their first column; round floats to 2 decimals; plain Python types only.
- Be robust to the drift seen in the input profiles: column names can change between occurrences
  (map them via an alias table, case-insensitive), numbers can arrive as text (pd.to_numeric
  errors="coerce"), rows can be empty. Raise ValueError with a clear message if a required column
  is missing.
- Keep it short and readable. No prints.

TESTS contract:
- 2-4 plain functions `def test_...():` using assert. No pytest import, no fixtures.
- `run` and `FakeCtx` are already defined in scope. You may import pandas.
- Build small DataFrames in memory. FakeCtx API:
{FAKE_CTX_API}
- Cover: the normal case with exact expected numbers, and one drift case (renamed columns or
  numbers as text).
"""

CODE_SCHEMA: dict = {
    "type": "object",
    "required": ["code", "tests"],
    "properties": {"code": {"type": "string"}, "tests": {"type": "string"}},
}

REPAIR_PROMPT = """\
Your previous code failed these checks:
{problems}

Fix every problem and return the full corrected JSON {{"code": "...", "tests": "..."}}."""

# ---- tutorial ---------------------------------------------------------------

TUTORIAL_HEADINGS = [
    "What it does",
    "What's automated",
    "What needs your approval",
    "What you give it",
    "What you get back",
    "Example",
    "Permissions used",
    "How to undo or delete",
    "Limits",
]

TUTORIAL_PROMPT = """\
Write TOOL.md, a one-page tutorial for a non-programmer, in Markdown.
Exactly these sections, in this order, each as "## <heading>":
## What it does
## What's automated
## What needs your approval
## What you give it
## What you get back
## Example
## Permissions used
## How to undo or delete
## Limits
Rules: at most 400 words in total, plain language, no code blocks, no Python.
- "What's automated" and "What needs your approval" list the AUTOMATION steps given below, word for
  word, split by their automation value ("auto" vs "approval"); write "Nothing." if a list is empty.
- "Permissions used" lists the scopes in REQUIRES in plain words (e.g. app:slack = post in Slack).
- "How to undo or delete": every confirmed run can be undone from the tool page (Undo on the run);
  the tool can be deleted any time and may be suggested again later unless you choose
  "Don't suggest again".
- The Example uses the real example run given below. Limits names what it does NOT handle.
Start with a "# <tool title>" line. Output only the Markdown.
"""
