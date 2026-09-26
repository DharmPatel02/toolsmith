"""P3: connected apps (permission grants) and the automation plan shown before anything is built."""

import os
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.automation import connectors
from app.automation.plan import automation_plan

router = APIRouter(tags=["p3-automation"])


def _user() -> str:
    return os.getenv("DEMO_USER_ID", "u_1")


class ConnectBody(BaseModel):
    scopes: list[str] | None = None


class PlanBody(BaseModel):
    signature: list[str]
    est_minutes_saved_week: float | None = None
    avg_minutes: float | None = None


@router.get("/connectors")
async def get_connectors() -> list[dict]:
    return await connectors.list_connectors(_user())


@router.post("/connectors/{app}/connect")
async def connect(app: str, body: ConnectBody | None = None) -> dict:
    try:
        return await connectors.start_connect(_user(), app, (body.scopes if body else None))
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/connectors/callback")
async def callback(state: str, code: str | None = None, error: str | None = None):
    """Where the app's consent page sends the browser back; lands on the web Connected apps page."""
    try:
        result = await connectors.complete(state, code, error)
    except LookupError as e:
        return RedirectResponse(
            f"{connectors.web_base()}/connectors?error={quote(str(e))}", status_code=303
        )
    except ConnectionError:
        return RedirectResponse(
            f"{connectors.web_base()}/connectors?error=token_exchange_failed", status_code=303
        )
    return RedirectResponse(
        f"{connectors.web_base()}/connectors?app={result['app']}&status={result['status']}",
        status_code=303,
    )


@router.post("/connectors/{app}/revoke")  # POST: the API's CORS allows GET/POST only
async def revoke(app: str) -> dict:
    if app not in connectors.APPS:
        raise HTTPException(404, f"unknown app {app}")
    return await connectors.revoke(_user(), app)


@router.post("/automation/plan")
async def plan(body: PlanBody) -> dict:
    """Step-by-step: what's automated, what waits for approval, which permissions are missing."""
    return automation_plan(body.model_dump(exclude_none=True), await connectors.granted(_user()))
