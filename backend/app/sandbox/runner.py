"""Phase 0 fixture stub. P2 owns its real implementation."""

from typing import Literal

from app.contracts import SandboxResult
from app.fixtures import require_stub


async def run_in_sandbox(
    code: str,
    entry: str,
    params: dict,
    inputs: dict[str, str],
    mode: Literal["dry_run", "live"],
    scopes: list[str],
    timeout_s: int = 30,
    deps: dict[str, str] | None = None,
) -> SandboxResult:
    require_stub()
    return SandboxResult(
        ok=False,
        output={},
        intended_writes=[],
        stdout="",
        error="Phase 0 stub: no code executed",
        duration_ms=0,
    )
