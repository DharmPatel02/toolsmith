"""Phase 0 vocabulary mapping; live vocabulary integration belongs to P1.1.10."""

import json

from app.config import ROOT
from app.fixtures import require_stub


def to_signature(verb: str, args_shape: dict) -> str:
    require_stub()
    vocab = json.loads((ROOT / "data/action_vocab_seed.json").read_text())
    canonical = next(
        (item["_id"] for item in vocab if verb == item["_id"] or verb in item["aliases"]), "other"
    )
    if canonical in ("file.open", "file.save", "file.download", "doc.read"):
        return f"{canonical}:{args_shape['ext']}" if args_shape.get("ext") else canonical
    return {"table.pivot": "table.pivot:2col", "table.rename": "table.rename:cols"}.get(
        canonical, canonical
    )
