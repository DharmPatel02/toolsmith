"""Unit-test kit for forged tools.

Forged tests are plain `def test_x():` functions that build small in-memory data, call
`run(FakeCtx(...), **params)` and assert on the result. `build_test_program` glues
tool code + FakeCtx + tests + a `run_tests` entry into one module, so the gate runs it
with the ordinary `run_in_sandbox(..., entry="run_tests")`; no special runner API.
"""
from __future__ import annotations

FAKE_CTX_API = """\
FakeCtx(tables: dict[str, DataFrame] = None, texts: dict[str, str] = None, pages: dict[url, html] = None)
  ctx.read_table(name) -> DataFrame copy of tables[name]
  ctx.read_text(name)  -> texts[name]
  ctx.fetch(url)       -> pages[url] (KeyError if missing)
  ctx.write_output(name, content) -> recorded in ctx.writes[name]
  ctx.call(tool, **kw) -> raises NotImplementedError"""

FAKE_CTX_SRC = '''
class FakeCtx:
    def __init__(self, tables=None, texts=None, pages=None):
        self.tables = tables or {}
        self.texts = texts or {}
        self.pages = pages or {}
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
        raise NotImplementedError("ctx.call is not available in unit tests")
'''

RUNNER_SRC = '''
def run_tests(ctx=None, **_):
    import traceback as _tb
    names = [n for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    failed = []
    for n in names:
        try:
            globals()[n]()
        except Exception as e:
            failed.append({"name": n, "error": (type(e).__name__ + ": " + str(e))[:300],
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
