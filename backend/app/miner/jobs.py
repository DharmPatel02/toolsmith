"""Worker entry point for mining a user's closed sessions."""

from worker import register

from app.miner.service import consolidate_user, mine_user


async def mine(payload: dict):
    user_id = payload.get("user_id")
    if not user_id:
        raise ValueError("mine job requires user_id")
    patterns = await mine_user(user_id)
    return {"patterns": len(patterns)}


register("mine", mine)


async def consolidate(payload: dict):
    user_id = payload.get("user_id")
    if not user_id:
        raise ValueError("consolidate job requires user_id")
    return await consolidate_user(user_id)


register("consolidate", consolidate)
