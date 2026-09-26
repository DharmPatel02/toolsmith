"""UC2 reference: "understand this paper" -> the same five param keys every time.

    python reference.py      # recompute expected/paperN_params.json from paperN.txt

Keys: title, method, datasets, metrics, main_result. Section names drift between papers
(Method vs APPROACH, Datasets vs DATA, Metrics vs EVALUATION METRICS) like week 3 in UC1;
the forged tool must absorb that. `method` is the first sentence of the method section,
`main_result` the first sentence of the results section.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPECTED = ROOT / "expected"
KEYS = ["title", "method", "datasets", "metrics", "main_result"]
SECTION_ALIASES = {
    "method": ["method", "approach", "methodology"],
    "datasets": ["datasets", "data", "benchmarks"],
    "metrics": ["metrics", "evaluation metrics", "evaluation"],
    "main_result": ["results", "findings"],
}
HEADING = re.compile(r"^\s*\d+\.?\s+([A-Za-z][A-Za-z ]+?)\s*$")


def sections(text: str) -> dict[str, str]:
    out, current = {}, None
    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            current = m.group(1).strip().lower()
            out[current] = ""
        elif current:
            out[current] += line.strip() + " "
    return {k: v.strip() for k, v in out.items()}


def first_sentence(s: str) -> str:
    m = re.match(r"(.+?[.!?])(\s|$)", s)
    return (m.group(1) if m else s).strip()


def extract(text: str) -> dict:
    title = re.search(r"(?im)^\s*title:\s*(.+)$", text).group(1).strip()
    secs = sections(text)
    out = {"title": title}
    for key, aliases in SECTION_ALIASES.items():
        body = next((secs[a] for a in aliases if a in secs), "")
        out[key] = first_sentence(body) if key in ("method", "main_result") else body
    return {k: out[k] for k in KEYS}


def main() -> None:
    EXPECTED.mkdir(exist_ok=True)
    for p in sorted(ROOT.glob("paper*.txt")):
        params = extract(p.read_text(encoding="utf-8"))
        (EXPECTED / f"{p.stem}_params.json").write_text(json.dumps(params, indent=1) + "\n", encoding="utf-8")
        print(p.name, "->", list(params))


if __name__ == "__main__":
    main()
