"""What a suggested automation will do, step by step, and what it needs (plan §1.1).

Deterministic (no LLM): each canonical step `domain.verb:argshape` is looked up in STEPS by its
`domain.verb`. The same plan is shown on the suggestion card, in the permission dialog before the
forge, and in the tool's one-page tutorial, so the three always agree.

    automation: "auto"     ToolSmith does it on every run
                "approval" ToolSmith prepares it; a person approves before it happens
                "manual"   stays with the user (ToolSmith can't or shouldn't do it)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Automation = Literal["auto", "approval", "manual"]


@dataclass(frozen=True)
class Step:
    label: str
    automation: Automation
    connector: str | None = None  # connectors.APPS key, "web" for allow-listed sites, None = local
    scope: str | None = None


STEPS: dict[str, Step] = {
    # files and tables (local, inside the sandbox)
    "file.open": Step("Open the input file", "auto"),
    "file.save": Step("Save the result", "auto"),
    "file.download": Step("Download the file", "auto"),
    "file.upload": Step("Upload a file", "approval"),
    "file.copy": Step("Copy the file", "auto"),
    "table.rename": Step("Rename columns", "auto"),
    "table.dropna": Step("Drop empty rows", "auto"),
    "table.cast": Step("Fix column types", "auto"),
    "table.pivot": Step("Pivot the table", "auto"),
    "table.filter": Step("Filter rows", "auto"),
    "table.join": Step("Match against the reference table", "auto"),
    "table.sort": Step("Sort rows", "auto"),
    "table.groupby": Step("Group and summarize", "auto"),
    "table.dedupe": Step("Remove duplicates", "auto"),
    "table.aggregate": Step("Aggregate totals", "auto"),
    "table.select": Step("Pick columns", "auto"),
    "table.compare": Step("Compare against the competitor", "auto"),
    "chart.bar": Step("Draw a bar chart", "auto"),
    "chart.line": Step("Draw a trend line", "auto"),
    "chart.scatter": Step("Draw a scatter plot", "auto"),
    "export.html": Step("Write the HTML report", "auto"),
    "export.pdf": Step("Write the PDF report", "auto"),
    "export.csv": Step("Write the CSV export", "auto"),
    "report.html": Step("Write the HTML report", "auto"),
    "doc.read": Step("Read the document", "auto"),
    "doc.extract": Step("Extract the key fields", "auto"),
    # web (allow-listed sites only, read-only)
    "web.navigate": Step("Open the site", "auto", "web", "read"),
    "web.fetch": Step("Fetch the pages", "auto", "web", "read"),
    "web.extract": Step("Read products and prices", "auto", "web", "read"),
    "web.click": Step("Click through the site", "auto", "web", "read"),
    "web.submit": Step("Submit a form on the site", "manual", "web", "write"),
    # email and invoices
    "email.open": Step("Read new invoices from the inbox", "auto", "email", "mail:read"),
    "email.reply": Step("Reply to the vendor", "approval", "email", "mail:send"),
    "msg.send": Step("Send an email", "approval", "email", "mail:send"),
    "pdf.extract": Step("Extract invoice number, lines and totals from the PDF", "auto"),
    "invoice.validate": Step("Check quantities and prices against the PO", "auto"),
    # notifications and trackers
    "tracker.upsert": Step("Add or update the tracker row", "auto", "tracker", "rows:write"),
    "slack.post": Step("Post an alert in Slack", "approval", "slack", "chat:write"),
    "jira.create": Step("Open a Jira ticket for the mismatch", "approval", "jira", "issues:write"),
}

UNKNOWN = Step("Step ToolSmith can't automate yet", "manual")


def verb_of(signature_step: str) -> str:
    return signature_step.split(":", 1)[0]


def automation_plan(pattern: dict, granted: dict[str, list[str]] | None = None) -> dict:
    """{steps, permissions, counts, est_minutes_saved_week} for a pattern / suggestion dict.

    `granted` maps connector app -> scopes the user has already granted (from `connectors`).
    """
    granted = granted or {}
    steps, needed = [], {}
    for raw in pattern.get("signature", []):
        step = STEPS.get(verb_of(raw), UNKNOWN)
        steps.append(
            {
                "step": raw,
                "label": step.label,
                "automation": step.automation,
                "connector": step.connector,
            }
        )
        if step.connector and step.scope and step.connector != "web":
            needed.setdefault(step.connector, [])
            if step.scope not in needed[step.connector]:
                needed[step.connector].append(step.scope)
    permissions = [
        {"connector": app, "scopes": scopes, "granted": set(scopes) <= set(granted.get(app, []))}
        for app, scopes in needed.items()
    ]
    if any(s["connector"] == "web" for s in steps):
        permissions.insert(
            0, {"connector": "web", "scopes": ["read allow-listed sites"], "granted": True}
        )
    counts = {
        kind: sum(s["automation"] == kind for s in steps) for kind in ("auto", "approval", "manual")
    }
    # the suggestion's own estimate; a raw pattern only knows minutes per run
    minutes = pattern.get("est_minutes_saved_week", pattern.get("avg_minutes") or 0)
    return {
        "steps": steps,
        "permissions": permissions,
        "counts": counts,
        "est_minutes_saved_week": minutes,
    }


def missing_permissions(plan: dict) -> list[dict]:
    return [p for p in plan["permissions"] if not p["granted"]]
