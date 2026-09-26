"""Phase 0 fixture stub. P2 owns its real implementation."""

from typing import Literal

from app.contracts import LLMResult
from app.fixtures import fixture


async def complete(
    tier: Literal["lean", "heavy", "vision"], messages: list[dict], json_schema: dict | None = None
) -> LLMResult:
    spec = fixture("candidate_uc1.json")["spec"]
    return LLMResult(
        text="Phase 0 fixture",
        json=spec,
        tokens_in=0,
        tokens_out=0,
        usd=0,
        model="fixture",
        cached=False,
    )
