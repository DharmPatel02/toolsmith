"""Race baseline (P2.3.3): a plain agent with no toolbox, solving the task from scratch."""
from app.forge.checks import ALLOWED_IMPORTS

BASELINE_PROMPT = f"""\
You are a data assistant with NO saved tools. Solve the user's request from scratch using the
functions you have: look at the inputs, write Python, run it, fix errors, then call `finish`.

`run_python` code must define `def run(ctx):` and return a dict. Read inputs only with
`ctx.read_table(name)` (pandas DataFrame) or `ctx.read_text(name)`; write files only with
`ctx.write_output(name, text)`. Allowed imports: {", ".join(sorted(ALLOWED_IMPORTS))}.
Return {{"summary": str, "tables": {{name: [row dicts]}}, "chart_spec": {{"type","x","y","title"}}}}.
Call `finish` with the final summary as soon as the result is right. Be brief.
"""

BASELINE_TOOLS = [
    {"type": "function", "function": {
        "name": "list_inputs", "description": "List the input files with their columns and row counts.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "preview_table", "description": "First rows of an input table.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "rows": {"type": "integer"}},
                       "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "run_python", "description": "Run Python in a sandbox. Must define def run(ctx) -> dict.",
        "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}}},
    {"type": "function", "function": {
        "name": "finish", "description": "Return the final answer.",
        "parameters": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}}},
]
