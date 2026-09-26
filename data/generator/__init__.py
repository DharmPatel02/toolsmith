"""Deterministic synthetic analyst history; not a substitute for screen recordings."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKFLOWS = {
    "uc1": [
        "file.open:xlsx",
        "table.rename:cols",
        "table.dropna",
        "table.cast",
        "table.pivot:2col",
        "chart.bar",
        "export.html",
    ],
    "uc3": [
        "web.fetch:html",
        "web.extract:list",
        "table.dedupe",
        "table.aggregate",
        "chart.line",
        "export.html",
    ],
    "uc2": ["doc.read:pdf", "doc.extract:params", "table.cast", "chart.line", "export.pdf"],
    "decoy_a": ["file.download:csv", "table.select", "table.sort", "export.csv"],
    "decoy_b": ["file.open:csv", "table.select", "table.filter"],
}
TITLES = {
    "uc1": "Build weekly sales dashboard",
    "uc3": "Scrape analyze and report competitor prices",
    "uc2": "Understand this paper and reproduce its simulation",
    "decoy_a": "Clean downloaded CSV files",
    "decoy_b": "Explore a different analysis workflow",
    "noise": "Unrelated browsing",
}


def generate(*, user_id="u_1", start="2026-09-07"):
    beginning = datetime.fromisoformat(start).replace(tzinfo=timezone.utc, hour=13)
    if beginning.weekday() != 0:
        raise ValueError("History must begin on a Monday")
    specs = [("uc1", day, 0) for day in (0, 7, 14)]
    specs += [("uc3", day, 1) for day in range(19) if day % 7 < 5]
    specs += [("uc2", day, 2) for day in (1, 9, 18)]
    specs += [("decoy_a", 12, hour - 5) for hour in range(6)]
    specs += [("decoy_b", day, 3) for day in (3, 8, 13, 17)]
    specs += [("noise", day, 5) for day in range(9)]
    assert len(specs) == 40
    events, truth = [], []
    counts = {}
    varied = [
        ["chart.bar", "file.save:html", "web.navigate", "web.click", "file.copy", "msg.send:email"],
        [
            "doc.read:txt",
            "doc.extract:params",
            "table.join",
            "table.groupby",
            "table.cast",
            "export.pdf",
        ],
        [
            "file.upload:json",
            "web.fetch:html",
            "web.extract:list",
            "web.submit:form",
            "table.dedupe",
            "export.html",
        ],
        [
            "table.rename:cols",
            "table.dropna",
            "table.pivot:2col",
            "chart.scatter",
            "chart.line",
            "export.csv",
        ],
    ]
    for label, day, hour in specs:
        counts[label] = counts.get(label, 0) + 1
        number = counts[label]
        session_id = f"{user_id}_{label}_{number}"
        timestamp = beginning + timedelta(days=day, hours=hour)
        signatures = WORKFLOWS.get(label, []).copy()
        if label == "decoy_b":
            signatures += varied[number - 1]
        paths = {"inputs": [], "outputs": []}
        if label == "uc1":
            paths = {
                "inputs": [f"data/artifacts/uc1/week{number}.xlsx"],
                "outputs": [
                    f"data/artifacts/uc1/expected/week{number}_pivot.csv",
                    f"data/artifacts/uc1/expected/week{number}_chart.json",
                ],
            }
        elif label == "uc2":
            paths["inputs"] = [f"data/artifacts/uc2/paper{1 + (number - 1) % 2}.txt"]
        elif label == "uc3":
            paths["inputs"] = ["data/artifacts/uc3/v1.html"]
        truth.append(
            {
                "session_id": session_id,
                "workflow": label,
                "started_at": timestamp.isoformat(),
                "expected": "mined" if label.startswith("uc") else "declined",
                "signature": signatures,
            }
        )
        for index in range(25):
            signature = signatures[index] if index < len(signatures) else "other"
            verb, _, shape = signature.partition(":")
            args = {"ext": shape} if verb.startswith(("file.", "doc.read")) else {}
            if label == "uc1" and index == 0:
                args.update(file=f"week{number}.xlsx", week=f"week{number}")
            if verb == "table.pivot":
                args.update(rows="Region", values="Amount", aggfunc="sum")
            if verb == "table.rename":
                args["columns"] = {"reg": "Region", "amt": "Amount"}
            screen = label == "uc1" and index < len(signatures)
            events.append(
                {
                    "ts": (timestamp + timedelta(seconds=index * 20)).isoformat(),
                    "meta": {"user_id": user_id, "source": "excel" if screen else "pandas"},
                    "session_id": session_id,
                    "action": verb,
                    "signature": signature,
                    "target": {"kind": "file" if verb.startswith("file.") else "table"},
                    "args_shape": args,
                    "intent_text": TITLES[label],
                    "duration_ms": 20000,
                    "cost": {"tokens": 720, "usd": 0.001},
                    "error": None,
                    "evidence": {
                        "tier": "T2" if screen else "T0",
                        "confidence": 0.95,
                        "frame_ids": [f"{session_id}_step_{index}"] if screen else [],
                        "needs_review": False,
                    },
                    "artifacts": paths if index == 0 else {},
                }
            )
    events.sort(key=lambda event: (event["ts"], event["session_id"]))
    logs_only = [event for event in events if event["evidence"]["tier"] != "T2"]
    return (
        events,
        logs_only,
        {
            "synthetic": True,
            "start": start,
            "sessions": truth,
            "counts": {
                "sessions": len(truth),
                "events": len(events),
                "logs_only_events": len(logs_only),
                "by_workflow": counts,
            },
        },
    )


def write_history(out: str, **kwargs):
    events, logs, truth = generate(**kwargs)
    path = Path(out)
    path.mkdir(parents=True, exist_ok=True)
    for name, rows in [("history.jsonl", events), ("history_logs_only.jsonl", logs)]:
        (path / name).write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    (path / "ground_truth.json").write_text(json.dumps(truth, indent=2) + "\n")
    return truth["counts"]
