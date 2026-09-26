"""Job registry and Atlas change-stream worker."""

import asyncio
import importlib
import logging
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from uuid import uuid4

from app.config import get_settings
from pymongo import ReturnDocument

# `python worker.py` and `import worker` must share one registry.
if __name__ == "__main__":
    sys.modules["worker"] = sys.modules[__name__]

Handler = Callable[[dict], Awaitable[object]]
_handlers: dict[str, Handler] = {}


def register(job_type: str, handler: Handler) -> None:
    if job_type in _handlers and _handlers[job_type] is not handler:
        raise ValueError(f"Handler already registered for {job_type}")
    _handlers[job_type] = handler


def discover_jobs() -> list[str]:
    from pathlib import Path

    import app

    modules = []
    for root in app.__path__:
        for path in sorted(Path(root).glob("*/jobs.py")):
            name = f"app.{path.parent.name}.jobs"
            importlib.import_module(name)
            modules.append(name)
    return modules


async def dispatch(job_type: str, payload: dict):
    if job_type not in _handlers:
        raise LookupError(f"No handler registered for {job_type}")
    return await _handlers[job_type](payload)


async def main():
    discover_jobs()
    if get_settings().stub_mode:
        print("Fixture worker: registry ready; API memory is process-local", flush=True)
        await asyncio.Event().wait()
    else:
        from app.db import close_client, get_db

        print("Atlas worker: change streams and idle-session closure started", flush=True)
        try:
            await asyncio.gather(
                consume_change_streams(get_db()),
                idle_session_loop(),
                policy_learner_loop(),
            )
        finally:
            await close_client()


async def idle_session_loop():
    while True:
        try:
            await close_idle_sessions()
        except Exception as exc:
            logging.error("Idle-session closure failed (%s)", type(exc).__name__)
        await asyncio.sleep(30)


async def close_idle_sessions(store=None, embed=None, now=None):
    from app.ingest.service import close_idle
    from app.ingest.store import get_store

    store = store if store is not None else get_store()
    result = []
    for user_id in await store.users_with_open_sessions():
        result.extend(await close_idle(user_id, store=store, embed=embed, now=now))
    return result


async def policy_learner_loop():
    while True:
        try:
            await learn_policies()
        except Exception as exc:
            logging.error("Policy learner failed (%s)", type(exc).__name__)
        await asyncio.sleep(120)


async def learn_policies(db=None, now=None):
    if db is None:
        from app.db import get_db

        db = get_db()
    from app.policy.service import learn_policy

    policy_ids = await db.policy.distinct("_id")
    users = {
        policy_id.split("policy:", 1)[1]
        for policy_id in policy_ids
        if isinstance(policy_id, str) and policy_id.startswith("policy:")
    }
    users.update(await db.events.distinct("user_id"))
    results = {}
    for user_id in sorted(user for user in users if user):
        results[user_id] = await learn_policy(user_id, db=db, now=now)
    return results


async def enqueue_job(db, job_type: str, payload: dict, *, job_id: str | None = None):
    document = {
        "_id": job_id or uuid4().hex,
        "type": job_type,
        "payload": payload,
        "status": "queued",
        "created_at": datetime.now(timezone.utc),
    }
    await db.jobs.insert_one(document)
    return document["_id"]


async def queue_mining_for_session(db, session: dict):
    session_id = session.get("_id")
    user_id = session.get("user_id")
    if not session_id or not user_id or session.get("status") != "closed":
        return None
    existing = await db.jobs.find_one(
        {
            "type": "mine",
            "payload.session_id": session_id,
            "status": {"$in": ["queued", "running"]},
        },
        {"_id": 1},
    )
    if existing:
        return existing["_id"]
    return await enqueue_job(
        db, "mine", {"user_id": user_id, "session_id": session_id}
    )


async def process_job_change(db, job: dict):
    job_id = job.get("_id")
    if not job_id:
        return
    claimed = await db.jobs.find_one_and_update(
        {"_id": job_id, "status": "queued"},
        {"$set": {"status": "running", "started_at": datetime.now(timezone.utc)}},
        return_document=ReturnDocument.AFTER,
    )
    if not claimed:
        return
    try:
        await dispatch(claimed["type"], claimed.get("payload", {}))
    except Exception as exc:
        await db.jobs.update_one(
            {"_id": job_id, "status": "running"},
            {"$set": {"status": "failed", "error": type(exc).__name__}},
        )
        logging.error("Job %s failed (%s)", job_id, type(exc).__name__)
    else:
        await db.jobs.update_one(
            {"_id": job_id, "status": "running"},
            {"$set": {"status": "done", "completed_at": datetime.now(timezone.utc)}},
        )


async def _flush_frame_batch(db, key, user_id, session_id, pending, debounce_s):
    current = asyncio.current_task()
    try:
        await asyncio.sleep(debounce_s)
        await enqueue_job(
            db,
            "interpret",
            {"user_id": user_id, "session_id": session_id},
        )
    finally:
        if pending.get(key) is current:
            pending.pop(key, None)


def schedule_frame_interpret(db, frame: dict, pending: dict, *, debounce_s: float = 5):
    user_id = frame.get("user_id")
    session_id = frame.get("session_id")
    if not user_id or not session_id:
        return
    key = (user_id, session_id)
    previous = pending.get(key)
    if previous and not previous.done():
        previous.cancel()
    pending[key] = asyncio.create_task(
        _flush_frame_batch(db, key, user_id, session_id, pending, debounce_s)
    )


async def process_run_change(change: dict, db=None):
    run = change.get("fullDocument") or {}
    tool_id = run.get("tool_id")
    if not tool_id:
        return False
    from app.trust.service import check_drift

    try:
        drifted = await check_drift(tool_id)
    except NotImplementedError:
        logging.info("Drift check not implemented by the trust service yet")
        return False
    if drifted:
        if db is None:
            from app.db import get_db

            db = get_db()
        await enqueue_job(db, "heal", {"tool_id": tool_id, "user_id": run.get("user_id")})
    return drifted


async def _watch(db, collection_name: str, pipeline: list, handler, *, full_document=None):
    collection = db[collection_name]
    options = {"full_document": full_document} if full_document else {}
    resume_token = None
    while True:
        try:
            watch_options = {**options}
            if resume_token is not None:
                watch_options["resume_after"] = resume_token
            async with await collection.watch(pipeline, **watch_options) as changes:
                async for change in changes:
                    await handler(change)
                    resume_token = changes.resume_token
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logging.error("%s change stream disconnected (%s)", collection_name, type(exc).__name__)
            await asyncio.sleep(2)


async def consume_change_streams(db):
    pending_frames = {}

    async def sessions_handler(change):
        await queue_mining_for_session(db, change.get("fullDocument") or {})

    async def jobs_handler(change):
        await process_job_change(db, change.get("fullDocument") or {})

    async def frames_handler(change):
        schedule_frame_interpret(db, change.get("fullDocument") or {}, pending_frames)

    async def runs_handler(change):
        await process_run_change(change, db=db)

    watchers = [
        _watch(
            db,
            "sessions",
            [{"$match": {"fullDocument.status": "closed"}}],
            sessions_handler,
            full_document="updateLookup",
        ),
        _watch(
            db,
            "jobs",
            [{"$match": {"fullDocument.status": "queued"}}],
            jobs_handler,
            full_document="updateLookup",
        ),
        _watch(
            db,
            "runs",
            [{"$match": {"operationType": "insert"}}],
            runs_handler,
            full_document="updateLookup",
        ),
        _watch(
            db,
            "frames",
            [{"$match": {"operationType": "insert"}}],
            frames_handler,
            full_document="updateLookup",
        ),
    ]
    try:
        await asyncio.gather(*watchers)
    finally:
        for task in pending_frames.values():
            task.cancel()
        if pending_frames:
            await asyncio.gather(*pending_frames.values(), return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
