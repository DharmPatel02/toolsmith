"""Concierge (P2.3.6): a small tool-calling chat over the user's memory and toolbox."""

CONCIERGE_PROMPT = """\
You are ToolSmith's concierge. You help one user with the tools ToolSmith built from their own
repeated work. You can:
- recall_episodes(query): past work sessions (date, what they did, minutes, tokens).
- search_tools(query): tools in their toolbox.
- run_tool(tool_id, params): run a tool as a DRY RUN preview (nothing is written).
- analyze_idea(text, confirm): check a new automation idea: already covered by a tool, or a spec.
  Only pass confirm=true after the user explicitly says to build it.
- submit_feedback(tool_id or pattern_id, decision, reason, diff): record what the user wants changed
  ("also export PDF", "don't touch the raw sheet") or why they reject something.
- approve_change(change_id): approve a pending guardrail change, only when the user asks to.

Rules: when asked WHY something was suggested or what happened before, call recall_episodes and
cite the dates (e.g. "on Mon 7 Sep, Mon 14 Sep and Mon 21 Sep you ..."). Never invent dates,
numbers or tools; only use what the functions return. Keep answers to 2-4 sentences.
Nothing is built, loosened or run for real without the user's explicit yes.
"""

CONCIERGE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "recall_episodes",
            "description": "Search the user's past work sessions.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_tools",
            "description": "Search the user's toolbox.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tool",
            "description": "Dry-run a tool (preview, nothing written).",
            "parameters": {
                "type": "object",
                "properties": {"tool_id": {"type": "string"}, "params": {"type": "object"}},
                "required": ["tool_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_idea",
            "description": "Analyze an automation idea: existing tool, or a spec to forge.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "confirm": {"type": "boolean"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_feedback",
            "description": "Record the user's feedback on a tool or suggestion.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_id": {"type": "string"},
                    "pattern_id": {"type": "string"},
                    "decision": {
                        "type": "string",
                        "enum": ["approve", "reject", "edit", "snooze", "ignore", "failed_run"],
                    },
                    "reason": {"type": "string"},
                    "diff": {"type": "string"},
                },
                "required": ["decision"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "approve_change",
            "description": "Approve a pending policy (guardrail) change.",
            "parameters": {
                "type": "object",
                "properties": {"change_id": {"type": "string"}},
                "required": ["change_id"],
            },
        },
    },
]
