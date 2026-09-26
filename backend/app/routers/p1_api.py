from datetime import datetime, time, timedelta, timezone
from math import sqrt
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pymongo import DESCENDING

from app.capture.service import ingest_capture_batch
from app.config import ROOT, get_settings
from app.contracts import (
    CaptureAck,
    CaptureBatch,
    Contract,
    EpisodeHit,
    FrameEvidence,
    Metrics,
    ObservationBatch,
    PolicyDoc,
    RunResult,
    ToolDetail,
    ToolSummary,
    ToolVersion,
    WhyResponse,
)
from app.db import get_db
from app.embeddings import embed
from app.events import publish, subscribe
from app.fixtures import fixture, require_demo_user
from app.ingest.service import ingest
from app.metrics.service import compute_metrics
from app.policy.service import approve_change, get_policy, record_change
from app.runtime.service import run_by_intent, run_tool

router = APIRouter()


def demo_user():
    user = get_settings().demo_user_id
    if get_settings().stub_mode:
        require_demo_user(user)
    return user


def check_tool(tool_id: str):
    tool = fixture("tool_uc1.json")
    if tool_id != tool["tool_id"]:
        raise HTTPException(404, "Unknown fixture tool")
    return tool


@router.get("/tools", response_model=list[ToolSummary])
async def tools():
    user_id = demo_user()
    if not get_settings().stub_mode:
        rows = await get_db().tools.find(
            {"user_id": user_id, "status": {"$ne": "deleted"}}
        ).sort("title", 1).to_list(length=100)
        return [_summary(row) for row in rows]
    tool = fixture("tool_uc1.json")
    return [{key: tool[key] for key in ToolSummary.model_fields}]


@router.get("/tools/{tool_id}", response_model=ToolDetail)
async def tool_detail(tool_id: str):
    user_id = demo_user()
    if not get_settings().stub_mode:
        return await _tool_detail(user_id, tool_id)
    return check_tool(tool_id)


@router.get("/tools/{tool_id}/versions", response_model=list[ToolVersion])
async def versions(tool_id: str):
    user_id = demo_user()
    if not get_settings().stub_mode:
        await _tool_detail(user_id, tool_id)
        rows = await get_db().tool_versions.find({"tool_id": tool_id}).sort(
            "version", DESCENDING
        ).to_list(length=100)
        return rows
    return [check_tool(tool_id)["version"]]


class RollbackRequest(Contract):
    version: int


def _summary(tool: dict) -> dict:
    data = {key: tool.get(key) for key in ToolSummary.model_fields}
    data["tool_id"] = str(tool.get("tool_id") or tool.get("_id"))
    data["name"] = data["name"] or data["tool_id"]
    data["title"] = data["title"] or data["name"]
    data["status"] = data["status"] or "active"
    data["trust"] = data["trust"] or "dry_run"
    data["runs"] = data["runs"] or 0
    data["success_rate"] = data["success_rate"] or 0
    data["p50_ms"] = data["p50_ms"] or 0
    data["minutes_saved"] = data["minutes_saved"] or 0
    return data


async def _tool_detail(user_id: str, tool_id: str) -> dict:
    db = get_db()
    tool = await db.tools.find_one(
        {"$or": [{"_id": tool_id}, {"tool_id": tool_id}], "user_id": user_id}
    )
    if not tool:
        raise HTTPException(404, "Unknown tool")
    ident = str(tool.get("tool_id") or tool.get("_id"))
    active = tool.get("active_version", 1)
    version = tool.get("version")
    if not version or version.get("version") != active:
        version = await db.tool_versions.find_one({"tool_id": ident, "version": active})
    if not version:
        raise HTTPException(404, "Active tool version not found")
    return {
        **_summary(tool),
        "user_id": user_id,
        "tier": tool.get("tier", "lean"),
        "active_version": active,
        "lineage": tool.get("lineage", {}),
        "version": version,
    }


@router.post("/tools/{tool_id}/rollback")
async def rollback(tool_id: str, body: RollbackRequest):
    user_id = demo_user()
    if get_settings().stub_mode:
        check_tool(tool_id)
        return {"ok": True}
    db = get_db()
    detail = await _tool_detail(user_id, tool_id)
    version = await db.tool_versions.find_one(
        {"tool_id": detail["tool_id"], "version": body.version}
    )
    if not version:
        raise HTTPException(404, "Unknown tool version")
    await db.tools.update_one(
        {"$or": [{"_id": tool_id}, {"tool_id": tool_id}], "user_id": user_id},
        {"$set": {"active_version": body.version, "version": version}},
    )
    return {"ok": True}


@router.post("/capture/batch", response_model=CaptureAck)
async def capture(batch: CaptureBatch):
    try:
        return await ingest_capture_batch(demo_user(), batch)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.post("/observations/bulk")
async def observations(batch: ObservationBatch):
    demo = get_settings().demo_user_id
    if batch.user_id not in (demo, demo + "_logs_only"):
        raise HTTPException(403, "Only the demo and ablation users may ingest")
    return await ingest(batch)


@router.get("/suggestions")
async def suggestions():
    user_id = demo_user()
    if not get_settings().stub_mode:
        db = get_db()
        policy = await db.policy.find_one({"_id": f"policy:{user_id}"})
        thresholds = (policy or {}).get("thresholds", {})
        cap = max(0, int(thresholds.get("max_suggestions_per_day", 3)))
        now = datetime.now(timezone.utc)
        day_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
        shown = await db.suggestion_impressions.count_documents(
            {"user_id": user_id, "shown_at": {"$gte": day_start}}
        )
        remaining = max(0, cap - shown)
        patterns = (
            await db.patterns.find(
                {
                    "user_id": user_id,
                    "status": "mined",
                    "$or": [{"cooldown_until": None}, {"cooldown_until": {"$lte": now}}],
                }
            )
            .sort("value", -1)
            .to_list(length=100)
        )
        output = []
        for pattern in patterns:
            if len(output) >= remaining:
                break
            signature = pattern.get("signature", [])
            rules = (policy or {}).get("rules", [])
            if any(
                rule.get("pattern_id") == pattern.get("_id")
                or (
                    rule.get("blocked_signatures")
                    and set(signature) & set(rule["blocked_signatures"])
                )
                for rule in rules
            ):
                continue
            query = " ".join([pattern.get("title", ""), *signature])
            vectors = await embed([query], input_type="query")
            vector = vectors[0] if vectors else []
            tools = await db.tools.find(
                {"user_id": user_id, "status": "active"},
                {"embedding": 1, "signature": 1},
            ).to_list(length=None)
            covered = False
            norm = sqrt(sum(value * value for value in vector))
            for tool in tools:
                tool_vector = tool.get("embedding") or []
                tool_norm = sqrt(sum(value * value for value in tool_vector))
                similarity = (
                    sum(a * b for a, b in zip(vector, tool_vector)) / (norm * tool_norm)
                    if norm and tool_norm and len(vector) == len(tool_vector)
                    else 0
                )
                if similarity >= float(thresholds.get("T_high", 0.82)) or (
                    signature and set(signature).issubset(set(tool.get("signature", [])))
                ):
                    covered = True
                    break
            if covered:
                continue
            output.append(
                {
                    "pattern_id": pattern["_id"],
                    "title": pattern.get("title", ""),
                    "reason": (
                        f"Repeated {pattern.get('support', 0)} times across "
                        f"{pattern.get('distinct_days', 0)} days"
                    ),
                    "support": pattern.get("support", 0),
                    "distinct_days": pattern.get("distinct_days", 0),
                    "est_minutes_saved_week": pattern.get("value", 0),
                    "value": pattern.get("value", 0),
                    "signature": signature,
                    "dynamic_params": pattern.get("dynamic_params", []),
                }
            )
        for item in output:
            impression_id = f"{user_id}:{now.date().isoformat()}:{item['pattern_id']}"
            await db.suggestion_impressions.update_one(
                {"_id": impression_id},
                {
                    "$setOnInsert": {
                        "_id": impression_id,
                        "user_id": user_id,
                        "pattern_id": item["pattern_id"],
                        "shown_at": now,
                    }
                },
                upsert=True,
            )
        return output
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
    user_id = demo_user()
    if not get_settings().stub_mode:
        rows = (
            await get_db()
            .patterns.find(
                {"user_id": user_id, "status": "declined"},
                {"_id": 1, "title": 1, "declined_reason": 1, "cooldown_until": 1},
            )
            .sort("value", -1)
            .to_list(length=100)
        )
        return rows
    return []


class SuggestionDecision(Contract):
    reason: str = ""
    never_for_scope: str | None = None
    edited_params: dict | None = None
    snooze_days: int | None = None


async def _pattern_for_decision(pattern_id: str):
    user_id = demo_user()
    if get_settings().stub_mode:
        pattern = fixture("pattern_uc1.json")
        if pattern_id != pattern["_id"]:
            raise LookupError("Unknown fixture pattern")
        return user_id, pattern
    pattern = await get_db().patterns.find_one({"_id": pattern_id, "user_id": user_id})
    if not pattern:
        raise LookupError("Unknown suggestion")
    return user_id, pattern


@router.post("/suggestions/{pattern_id}/accept")
async def accept_suggestion(pattern_id: str, body: SuggestionDecision):
    user_id, pattern = await _pattern_for_decision(pattern_id)
    if get_settings().stub_mode:
        return {"ok": True, "job_id": f"forge:{pattern_id}"}
    now = datetime.now(timezone.utc)
    job_id = f"forge:{user_id}:{pattern_id}"
    await get_db().jobs.update_one(
        {"_id": job_id},
        {
            "$setOnInsert": {
                "_id": job_id,
                "type": "forge",
                "payload": {
                    "user_id": user_id,
                    "pattern_id": pattern_id,
                    "edited_params": body.edited_params or {},
                },
                "status": "queued",
                "created_at": now,
            }
        },
        upsert=True,
    )
    await get_db().patterns.update_one(
        {"_id": pattern_id, "user_id": user_id},
        {"$set": {"status": "accepted", "accepted_at": now}},
    )
    await publish(user_id, "forge_started", {"pattern_id": pattern_id, "job_id": job_id})
    return {"ok": True, "job_id": job_id}


@router.post("/suggestions/{pattern_id}/decline")
async def decline_suggestion(pattern_id: str, body: SuggestionDecision):
    user_id, pattern = await _pattern_for_decision(pattern_id)
    policy = await get_policy(user_id)
    cooldowns = policy.thresholds.get("cooldown_days", [7, 14, 30])
    now = datetime.now(timezone.utc)
    if get_settings().stub_mode:
        return {"ok": True, "cooldown_until": (now + timedelta(days=cooldowns[0])).isoformat()}
    db = get_db()
    prior = await db.feedback.count_documents(
        {"user_id": user_id, "pattern_id": pattern_id, "kind": "decline"}
    )
    days = cooldowns[min(prior, len(cooldowns) - 1)]
    feedback_id = f"feedback:{uuid4().hex}"
    feedback = {
        "_id": feedback_id,
        "user_id": user_id,
        "pattern_id": pattern_id,
        "kind": "decline",
        "reason": body.reason,
        "edited_params": body.edited_params or {},
        "created_at": now,
    }
    await db.feedback.insert_one(feedback)
    await db.patterns.update_one(
        {"_id": pattern_id, "user_id": user_id},
        {
            "$set": {
                "status": "declined",
                "declined_reason": body.reason or "declined",
                "cooldown_until": now + timedelta(days=days),
            }
        },
    )
    change = None
    if body.never_for_scope:
        rule = {
            "scope": body.never_for_scope,
            "pattern_id": pattern_id,
            "blocked_signatures": pattern.get("signature", []),
            "origin": "feedback",
        }
        change = await record_change(
            user_id,
            "rules",
            [*policy.rules, rule],
            "tighten",
            f"Never suggest this workflow for {body.never_for_scope}",
            [feedback_id],
        )
    return {
        "ok": True,
        "feedback_id": feedback_id,
        "cooldown_until": (now + timedelta(days=days)).isoformat(),
        "policy_change_id": change.id if change else None,
    }


@router.post("/suggestions/{pattern_id}/snooze")
async def snooze_suggestion(pattern_id: str, body: SuggestionDecision):
    user_id, _ = await _pattern_for_decision(pattern_id)
    days = max(1, min(body.snooze_days or 7, 90))
    until = datetime.now(timezone.utc) + timedelta(days=days)
    if not get_settings().stub_mode:
        await get_db().patterns.update_one(
            {"_id": pattern_id, "user_id": user_id},
            {"$set": {"cooldown_until": until, "snoozed_at": datetime.now(timezone.utc)}},
        )
    return {"ok": True, "cooldown_until": until.isoformat()}


@router.get("/suggestions/{pattern_id}/why", response_model=WhyResponse)
async def why(pattern_id: str):
    user_id = demo_user()
    if get_settings().stub_mode:
        if pattern_id != "pat_uc1":
            raise HTTPException(404, "Unknown fixture pattern")
        return fixture("why_uc1.json")
    db = get_db()
    pattern = await db.patterns.find_one({"_id": pattern_id, "user_id": user_id})
    if not pattern:
        raise HTTPException(404, "Unknown suggestion")
    session_ids = pattern.get("evidence_session_ids", [])
    sessions = await db.sessions.find({"_id": {"$in": session_ids}, "user_id": user_id}).to_list(
        length=None
    )
    episodes = [
        EpisodeHit(
            session_id=session["_id"],
            date=session["started_at"],
            intent_summary=session.get("intent_summary", ""),
            minutes=session.get("minutes", 0),
            tokens=session.get("tokens", 0),
            score=1,
        )
        for session in sessions
    ]
    frames = (
        await db.frames.find({"user_id": user_id, "session_id": {"$in": session_ids}})
        .sort("ts", 1)
        .to_list(length=None)
    )
    representative = {}
    for frame in frames:
        day = frame["ts"].date().isoformat()
        representative.setdefault(day, frame)
    evidence = [
        FrameEvidence(
            frame_id=frame["_id"],
            ts=frame["ts"],
            thumb_url=f"/frames/{frame['_id']}/thumb",
            verb=(frame.get("label") or {}).get("verb", frame.get("trigger", "captured")),
        )
        for frame in representative.values()
    ]
    return WhyResponse(episodes=episodes, frames=evidence)


@router.get("/frames/{frame_id}/thumb")
async def thumbnail(frame_id: str):
    user_id = demo_user()
    if not get_settings().stub_mode:
        frame = await get_db().frames.find_one({"_id": frame_id, "user_id": user_id}, {"thumb": 1})
        if not frame:
            raise HTTPException(404, "Unknown frame")
        from fastapi.responses import Response

        return Response(frame.get("thumb", b""), media_type="image/webp")
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


@router.post("/policy/changes/{change_id}/approve")
async def approve_policy_change(change_id: str):
    try:
        return {"ok": True, "change": await approve_change(demo_user(), change_id)}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/consolidate")
async def consolidate():
    user_id = demo_user()
    job_id = f"consolidate:{uuid4().hex}"
    if get_settings().stub_mode:
        return {"job_id": job_id}
    await get_db().jobs.insert_one(
        {
            "_id": job_id,
            "type": "consolidate",
            "payload": {"user_id": user_id},
            "status": "queued",
            "created_at": datetime.now(timezone.utc),
        }
    )
    return {"job_id": job_id}


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
