from app.contracts import Metrics
from app.fixtures import fixture, require_demo_user


async def compute_metrics(user_id: str) -> Metrics:
    require_demo_user(user_id)
    return Metrics(**fixture("metrics.json"))
