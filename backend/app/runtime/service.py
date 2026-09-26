from app.contracts import RunResult
from app.fixtures import fixture, require_demo_user


async def run_by_intent(user_id: str, intent: str, inputs: dict) -> RunResult:
    require_demo_user(user_id)
    return RunResult(**fixture("run_result.json"))


async def run_tool(user_id: str, tool_id: str, params: dict, confirm: bool = False) -> RunResult:
    require_demo_user(user_id)
    if tool_id != "tool_uc1":
        raise LookupError("Unknown fixture tool")
    # Even confirm=True never executes code in Phase 0.
    return RunResult(**fixture("run_result.json"))
