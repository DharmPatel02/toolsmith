from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from app.capture.service import ingest_capture_batch
from app.config import ROOT, get_settings
from app.contracts import (
    CaptureAck,
    CaptureBatch,
    Contract,
    Metrics,
    ObservationBatch,
    PolicyDoc,
    RunResult,
    ToolDetail,
    ToolSummary,
    ToolVersion,
    WhyResponse,
)
from app.events import subscribe
from app.fixtures import fixture, require_demo_user
from app.ingest.service import ingest
from app.metrics.service import compute_metrics
from app.policy.service import get_policy
from app.runtime.service import run_by_intent, run_tool

router = APIRouter()


def demo_user():
    user = get_settings().demo_user_id
    require_demo_user(user)
    return user


def check_tool(tool_id: str):
    tool = fixture("tool_uc1.json")
    if tool_id != tool["tool_id"]:
        raise HTTPException(404, "Unknown fixture tool")
    return tool


@router.get("/tools", response_model=list[ToolSummary])
async def tools():
    demo_user()
    tool = fixture("tool_uc1.json")
    return [{key: tool[key] for key in ToolSummary.model_fields}]


@router.get("/tools/{tool_id}", response_model=ToolDetail)
async def tool_detail(tool_id: str):
    demo_user()
    return check_tool(tool_id)


@router.get("/tools/{tool_id}/versions", response_model=list[ToolVersion])
async def versions(tool_id: str):
    demo_user()
    return [check_tool(tool_id)["version"]]


@router.post("/capture/batch", response_model=CaptureAck)
async def capture(batch: CaptureBatch):
    try:
        return await ingest_capture_batch(demo_user(), batch)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/observations/bulk")
async def observations(batch: ObservationBatch):
    demo = get_settings().demo_user_id
    if batch.user_id not in (demo, demo + "_logs_only"):
        raise HTTPException(403, "Only the demo and ablation users may ingest")
    return await ingest(batch)


@router.get("/suggestions")
async def suggestions():
    demo_user()
    pattern = fixture("pattern_uc1.json")
    return [
        {
            "pattern_id": pattern["_id"],
            "title": pattern["title"],
            "reason": "Phase 0 fixture: repeated on three Mondays",
            "support": pattern["support"],
            "distinct_days": pattern["distinct_days"],
            "est_minutes_saved_week": 9,
            "value": pattern["value"],
            "signature": pattern["signature"],
            "dynamic_params": pattern["dynamic_params"],
        }
    ]


@router.get("/suggestions/declined")
async def declined():
    demo_user()
    return []


@router.get("/suggestions/{pattern_id}/why", response_model=WhyResponse)
async def why(pattern_id: str):
    demo_user()
    if pattern_id != "pat_uc1":
        raise HTTPException(404, "Unknown fixture pattern")
    return fixture("why_uc1.json")


@router.get("/frames/{frame_id}/thumb")
async def thumbnail(frame_id: str):
    demo_user()
    if frame_id not in {item["frame_id"] for item in fixture("why_uc1.json")["frames"]}:
        raise HTTPException(404, "Unknown fixture frame")
    return FileResponse(ROOT / "fixtures/frame_1.webp", media_type="image/webp")


class IntentRequest(Contract):
    intent: str
    inputs: dict


class RunRequest(Contract):
    params: dict
    confirm: bool = False


@router.post("/run", response_model=RunResult)
async def intent_run(body: IntentRequest):
    return await run_by_intent(demo_user(), body.intent, body.inputs)


@router.post("/tools/{tool_id}/run", response_model=RunResult)
async def tool_run(tool_id: str, body: RunRequest):
    return await run_tool(demo_user(), tool_id, body.params, body.confirm)


@router.get("/policy", response_model=PolicyDoc)
async def policy():
    return await get_policy(demo_user())


@router.get("/metrics", response_model=Metrics)
async def metrics():
    return await compute_metrics(demo_user())


@router.get("/events")
async def events():
    return StreamingResponse(
        subscribe(demo_user()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
