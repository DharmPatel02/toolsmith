"""Concierge (P2.3.6): a small tool-calling chat over the user's memory and toolbox."""

CONCIERGE_PROMPT = """\
You are ToolSmith's concierge. You help one user with the tools ToolSmith built from their own
repeated work. You can:
- recall_episodes(query): past work sessions (date, what they did, minutes, tokens).
- search_tools(query): tools in their toolbox.
- run_tool(tool_id, params): run a tool as a DRY RUN preview (nothing is written).

Rules: when asked WHY something was suggested or what happened before, call recall_episodes and
cite the dates (e.g. "on Mon 7 Sep, Mon 14 Sep and Mon 21 Sep you ..."). Never invent dates,
numbers or tools; only use what the functions return. Keep answers to 2-4 sentences.
"""

CONCIERGE_TOOLS = [
    {"type": "function", "function": {
        "name": "recall_episodes", "description": "Search the user's past work sessions.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "search_tools", "description": "Search the user's toolbox.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "run_tool", "description": "Dry-run a tool (preview, nothing written).",
        "parameters": {"type": "object", "properties": {"tool_id": {"type": "string"}, "params": {"type": "object"}},
                       "required": ["tool_id"]}}},
]
