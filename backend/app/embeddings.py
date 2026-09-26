"""P1 Phase 0 placeholder. P2 owns the real Voyage implementation."""

from app.fixtures import require_stub


async def embed(texts: list[str], input_type: str = "document") -> list[list[float]]:
    require_stub()
    return [[1.0] + [0.0] * 1023 for _ in texts]


async def embed_multimodal(items: list[dict]) -> list[list[float]]:
    require_stub()
    return [[1.0] + [0.0] * 1023 for _ in items]
