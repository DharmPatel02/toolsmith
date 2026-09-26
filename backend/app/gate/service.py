"""Phase 0 fixture stub. P2 owns its real implementation."""

from app.contracts import Verdict
from app.fixtures import fixture


async def run_gate(candidate_id: str) -> Verdict:
    candidate = fixture("candidate_uc1.json")
    if candidate_id != candidate["_id"]:
        raise LookupError("Unknown fixture candidate")
    return Verdict(**candidate["verdict"])
