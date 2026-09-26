"""Unit-test kit for forged tools.

Forged tests are plain `def test_x():` functions that build small in-memory data, call
`run(FakeCtx(...), **params)` and assert on the result. `build_test_program` glues
tool code + FakeCtx + tests + a `run_tests` entry into one module, so the gate runs it
with the ordinary `run_in_sandbox(..., entry="run_tests")`; no special runner API.
"""
from __future__ import annotations

FAKE_CTX_API = """\
FakeCtx(tables: dict[str, DataFrame] = None, texts: dict[str, str] = None, pages: dict[url, html] = None,
        calls: dict[tool_name, function(**kw) -> dict] = None)
  ctx.read_table(name) -> DataFrame copy of tables[name]
  ctx.read_text(name)  -> texts[name]
  ctx.fetch(url)       -> pages[url] (KeyError if missing)
  ctx.write_output(name, content) -> recorded in ctx.writes[name]
  ctx.call(tool, **kw) -> calls[tool](**kw)  (fake a dependency tool; missing -> NotImplementedError)"""

FAKE_CTX_SRC = '''
class FakeCtx:
    def __init__(self, tables=None, texts=None, pages=None, calls=None):
        self.tables = tables or {}
        self.texts = texts or {}
        self.pages = pages or {}
        self.calls = calls or {}
        self.writes = {}

    def read_table(self, name):
        return self.tables[name].copy()

    def read_text(self, name):
        return self.texts[name]

    def fetch(self, url):
        return self.pages[url]

    def write_output(self, name, content):
        self.writes[name] = content

    def call(self, tool, **kw):
        if tool not in self.calls:
            raise NotImplementedError(f"no fake for dependency {tool!r}: FakeCtx(calls={{...}})")
        return self.calls[tool](**kw)
'''

RUNNER_SRC = '''
def _explain_assert(e):
    """pytest-style: for a failed `assert a <op> b`, re-evaluate both sides in the failing
    frame so the repair prompt sees the actual values, not a bare AssertionError."""
    import ast as _ast
    import inspect as _inspect
    import textwrap as _textwrap
    tb = e.__traceback__
    while tb.tb_next:
        tb = tb.tb_next
    fr = tb.tb_frame
    try:
        lines, start = _inspect.getsourcelines(fr.f_code)
        tree = _ast.parse(_textwrap.dedent("".join(lines)))
        rel = tb.tb_lineno - start + 1
        env = {**fr.f_globals, **fr.f_locals}

        def val(expr):
            return repr(eval(compile(_ast.Expression(expr), "<assert>", "eval"), env))[:400]
        for node in _ast.walk(tree):
            if not (isinstance(node, _ast.Assert) and node.lineno <= rel <= node.end_lineno):
                continue
            t = node.test.operand if isinstance(node.test, _ast.UnaryOp) else node.test
            if isinstance(t, _ast.Compare) and len(t.ops) == 1:
                return f" | {_ast.unparse(t.left)[:80]} was {val(t.left)}; expected {val(t.comparators[0])}"
            if isinstance(t, _ast.Call) and isinstance(t.func, _ast.Attribute):  # x.startswith("<html>")
                return f" | {_ast.unparse(t.func.value)[:80]} was {val(t.func.value)}"
            return f" | {_ast.unparse(t)[:80]} was {val(t)}"
    except Exception:
        pass
    return ""


def run_tests(ctx=None, **_):
    import traceback as _tb
    names = [n for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    failed = []
    for n in names:
        try:
            globals()[n]()
        except Exception as e:
            why = _explain_assert(e) if isinstance(e, AssertionError) else ""
            failed.append({"name": n, "error": (type(e).__name__ + ": " + str(e))[:300] + why,
                           "trace": _tb.format_exc()[-800:]})
    return {"total": len(names), "passed": len(names) - len(failed), "failed": failed}
'''


def build_test_program(code: str, tests: str) -> str:
    return (f"{code}\n\n# ---- FakeCtx ----\n{FAKE_CTX_SRC}\n\n# ---- tests ----\n{tests}\n\n"
            f"# ---- runner ----\n{RUNNER_SRC}")


def run_tests_locally(code: str, tests: str) -> dict:
    """In-process run, for P2's own tests only. The gate uses the sandbox."""
    ns: dict = {"__name__": "forged_tool"}
    exec(compile(build_test_program(code, tests), "forged_tool.py", "exec"), ns)  # noqa: S102
    return ns["run_tests"]()
