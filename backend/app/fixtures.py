"""Explicit Phase 0 fixtures; never silently substitute for live services."""

import json

from app.config import ROOT, get_settings


def require_stub() -> None:
    if not get_settings().stub_mode:
        raise NotImplementedError("Phase 0 stub: live implementation is not available yet")


def fixture(name: str):
    require_stub()
    return json.loads((ROOT / "fixtures" / name).read_text())


def require_demo_user(user_id: str) -> None:
    require_stub()
    if user_id != get_settings().demo_user_id:
        raise PermissionError("Phase 0 fixtures are available only for the demo user")
