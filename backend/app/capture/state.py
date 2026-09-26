"""Capture pause state for fixture and Atlas modes."""

from app.config import get_settings
from app.db import get_db

paused_users: set[str] = set()


async def is_paused(user_id: str) -> bool:
    if get_settings().stub_mode:
        return user_id in paused_users
    state = await get_db().capture_state.find_one({"_id": user_id}, {"paused": 1})
    return bool(state and state.get("paused"))


async def set_paused(user_id: str, paused: bool) -> None:
    if get_settings().stub_mode:
        (paused_users.add if paused else paused_users.discard)(user_id)
        return
    await get_db().capture_state.update_one(
        {"_id": user_id}, {"$set": {"user_id": user_id, "paused": paused}}, upsert=True
    )
