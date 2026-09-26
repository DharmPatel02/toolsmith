"""Development-only history reset; never deletes Atlas data."""

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.contracts import Contract
from app.fixtures import require_stub
from app.ingest.store import memory_store

router = APIRouter()


class ResetHistory(Contract):
    user_id: str


@router.post("/dev/reset-history")
async def reset_history(body: ResetHistory):
    require_stub()
    demo = get_settings().demo_user_id
    if body.user_id not in (demo, demo + "_logs_only"):
        raise HTTPException(403, "Only demo history may be reset")
    for collection in (
        memory_store.events,
        memory_store.sessions,
        memory_store.patterns,
        memory_store.policies,
    ):
        collection.pop(body.user_id, None)
    return {"ok": True}
