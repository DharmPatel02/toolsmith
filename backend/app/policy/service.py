from uuid import uuid4

from app.contracts import PolicyChange, PolicyDoc
from app.fixtures import fixture, require_demo_user


async def get_policy(user_id: str) -> PolicyDoc:
    require_demo_user(user_id)
    return PolicyDoc(**fixture("policy.json"))


async def record_change(
    user_id: str, field: str, new, direction: str, because: str, origin_ids: list[str]
) -> PolicyChange:
    require_demo_user(user_id)
    policy = fixture("policy.json")
    old = policy
    for key in field.split("."):
        old = old.get(key) if isinstance(old, dict) else None
    return PolicyChange(
        id=f"change_fixture_{uuid4().hex}",
        field=field,
        old=old,
        new=new,
        direction=direction,
        because=because,
        origin_feedback_ids=origin_ids,
        status="pending" if direction == "loosen" else "applied",
    )
