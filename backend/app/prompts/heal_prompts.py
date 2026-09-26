"""Heal prompt (P2.3.2): diagnose why a promoted tool broke and write version v+1."""
from app.forge.checks import ALLOWED_IMPORTS
from app.gate.testkit import FAKE_CTX_API

HEAL_PROMPT = f"""\
A tool that used to work now fails. You get its code, the error, the page/input it worked on
before (OLD) and the page/input it fails on now (NEW). The data is the same; the layout changed.

1. Diagnose in one or two sentences what changed (e.g. "class `.price` renamed to `.card-price`").
2. Rewrite the code so it works on BOTH the OLD and the NEW input and returns exactly the same
   output shape and values as before. Prefer selectors that survive the next small change
   (several fallbacks, text/role-based matching) over one brittle class name.
3. Update the tests: keep the old case, add one for the new layout.

Output JSON {{"diagnosis": "...", "code": "...", "tests": "..."}}.

Code contract: top-level `def run(ctx, **params) -> dict`; inputs only through ctx
(`ctx.fetch(url)`, `ctx.read_table`, `ctx.read_text`); allowed imports:
{", ".join(sorted(ALLOWED_IMPORTS))}; no open/os/eval; keep the same params and return shape.
Tests: plain `def test_...():` functions with assert; `run` and `FakeCtx` are in scope. FakeCtx API:
{FAKE_CTX_API}
"""

HEAL_SCHEMA: dict = {
    "type": "object",
    "required": ["diagnosis", "code", "tests"],
    "properties": {"diagnosis": {"type": "string"}, "code": {"type": "string"}, "tests": {"type": "string"}},
}


def heal_user_message(code: str, tests: str, error: str, old_input: str, new_input: str,
                      expected: object) -> str:
    return (f"CODE:\n{code}\n\nTESTS:\n{tests}\n\nERROR ON NEW INPUT:\n{error[-1500:]}\n\n"
            f"OLD INPUT (worked):\n{old_input[:6000]}\n\nNEW INPUT (fails):\n{new_input[:6000]}\n\n"
            f"EXPECTED OUTPUT TABLES (same for both):\n{expected}")
