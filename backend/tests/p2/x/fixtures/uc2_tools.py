"""UC2 tools for composition tests: `extract_method` (a promoted tool) and `paper_digest`
(a composed tool that calls it with ctx.call)."""

EXTRACT_METHOD = '''
import re

ALIASES = ["method", "approach", "methodology"]
HEADING = re.compile(r"^\\s*\\d+\\.?\\s+([A-Za-z][A-Za-z ]+?)\\s*$")


def sections(text):
    out, cur = {}, None
    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            cur = m.group(1).strip().lower()
            out[cur] = ""
        elif cur:
            out[cur] += line.strip() + " "
    return out


def run(ctx, paper):
    body = next((v for k, v in sections(ctx.read_text(paper)).items() if k in ALIASES), "").strip()
    m = re.match(r"(.+?[.!?])(\\s|$)", body)
    method = (m.group(1) if m else body).strip()
    return {"summary": method[:80], "params": {"method": method}}
'''

PAPER_DIGEST = '''
import re

ALIASES = {"datasets": ["datasets", "data", "benchmarks"], "metrics": ["metrics", "evaluation metrics", "evaluation"],
           "main_result": ["results", "findings"]}
HEADING = re.compile(r"^\\s*\\d+\\.?\\s+([A-Za-z][A-Za-z ]+?)\\s*$")


def sections(text):
    out, cur = {}, None
    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            cur = m.group(1).strip().lower()
            out[cur] = ""
        elif cur:
            out[cur] += line.strip() + " "
    return {k: v.strip() for k, v in out.items()}


def first(s):
    m = re.match(r"(.+?[.!?])(\\s|$)", s)
    return (m.group(1) if m else s).strip()


def run(ctx, paper):
    text = ctx.read_text(paper)
    secs = sections(text)
    params = {"title": re.search(r"(?im)^\\s*title:\\s*(.+)$", text).group(1).strip(),
              "method": ctx.call("extract_method", paper=paper)["params"]["method"]}
    for key, names in ALIASES.items():
        body = next((secs[n] for n in names if n in secs), "")
        params[key] = first(body) if key == "main_result" else body
    return {"summary": params["title"], "params": params}
'''

PAPER_DIGEST_TESTS = '''
def test_uses_dependency():
    page = "Title: T\\n1 Data\\nD1.\\n2 Metrics\\nM1.\\n3 Results\\nR1. more\\n"
    out = run(FakeCtx(texts={"paper": page}, calls={"extract_method": lambda paper: {"params": {"method": "X."}}}),
              paper="paper")
    assert out["params"] == {"title": "T", "method": "X.", "datasets": "D1.", "metrics": "M1.", "main_result": "R1."}
'''
