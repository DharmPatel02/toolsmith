import asyncio
import base64
import importlib
import json
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.config import ROOT, get_settings
from app.contracts import (
    Candidate,
    CaptureBatch,
    FrameLabel,
    Metrics,
    Pattern,
    PolicyDoc,
    RaceStep,
    RunResult,
    ToolDetail,
    WhyResponse,
)
from app.db import initialize_database
from app.events import publish, subscribe
from app.fixtures import fixture
from app.main import app, discover_routers
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError


@pytest.fixture(autouse=True)
def stub_settings(monkeypatch):
    monkeypatch.setenv("STUB_MODE", "true")
    monkeypatch.setenv("DEMO_USER_ID", "u_1")
    monkeypatch.setenv("CAPTURE_ALLOWED_ORIGINS", "http://localhost:8081")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize(
    "name, model",
    [
        ("pattern_uc1.json", Pattern),
        ("capture_batch.json", CaptureBatch),
        ("why_uc1.json", WhyResponse),
        ("tool_uc1.json", ToolDetail),
        ("candidate_uc1.json", Candidate),
        ("policy.json", PolicyDoc),
        ("run_result.json", RunResult),
        ("metrics.json", Metrics),
    ],
)
def test_shared_fixtures_validate(name, model):
    model.model_validate(fixture(name))


def test_race_fixtures():
    steps = [
        RaceStep(**json.loads(line)["data"])
        for line in (ROOT / "fixtures/race.jsonl").read_text().splitlines()
    ]
    assert {step.side for step in steps if step.done} == {"baseline", "tool"}


def test_tools_and_capture_acceptance(client):
    response = client.get("/tools")
    assert response.status_code == 200
    assert response.headers["X-ToolSmith-Mode"] == "fixture"
    assert response.json()[0]["tool_id"] == fixture("tool_uc1.json")["tool_id"]
    response = client.post("/capture/batch", json=fixture("capture_batch.json"))
    assert response.status_code == 200
    assert response.json() == {
        "ui_events": 3,
        "frames_kept": 2,
        "frames_dropped": 0,
        "paused": False,
    }


@pytest.mark.parametrize(
    "origin", ["https://evil.example", "http://localhost:8081.evil.test", "http://localhost:8082"]
)
def test_capture_rejects_other_origins(client, origin):
    batch = fixture("capture_batch.json")
    batch["events"][0]["url_template"] = origin + "/products"
    assert client.post("/capture/batch", json=batch).status_code == 403


def test_capture_frame_origin_is_allow_listed(client):
    batch = fixture("capture_batch.json")
    batch["frames"][0]["url_template"] = "https://evil.example/page"
    assert client.post("/capture/batch", json=batch).status_code == 403


def test_structured_capture_fusion_keeps_frame_evidence():
    from app.capture.service import _observation

    batch = CaptureBatch.model_validate(fixture("capture_batch.json"))
    event = batch.events[0]
    observation = _observation(batch.user_id, batch.capture_session_id, event, ["frame_1"])
    assert observation.evidence.tier == "T1"
    assert observation.evidence.frame_ids == ["frame_1"]


async def test_live_why_uses_user_scoped_sessions_and_one_frame_per_day(monkeypatch):
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock, MagicMock

    import app.routers.p1_api as api

    monkeypatch.setenv("STUB_MODE", "false")
    get_settings.cache_clear()
    db = MagicMock()
    db.patterns.find_one = AsyncMock(
        return_value={"_id": "pat_x", "user_id": "u_1", "evidence_session_ids": ["s1"]}
    )
    sessions_cursor = MagicMock()
    sessions_cursor.to_list = AsyncMock(
        return_value=[
            {
                "_id": "s1",
                "started_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
                "intent_summary": "Export a report",
                "minutes": 4,
                "tokens": 10,
            }
        ]
    )
    db.sessions.find.return_value = sessions_cursor
    frame_cursor = MagicMock()
    frame_cursor.sort.return_value.to_list = AsyncMock(
        return_value=[
            {
                "_id": "f1",
                "ts": datetime(2026, 9, 1, tzinfo=timezone.utc),
                "trigger": "click",
                "label": {"verb": "web.click"},
            },
            {
                "_id": "f2",
                "ts": datetime(2026, 9, 1, 0, 0, 1, tzinfo=timezone.utc),
                "trigger": "heartbeat",
            },
        ]
    )
    db.frames.find.return_value = frame_cursor
    monkeypatch.setattr(api, "get_db", lambda: db)
    try:
        response = await api.why("pat_x")
        assert len(response.episodes) == 1
        assert [frame.frame_id for frame in response.frames] == ["f1"]
        assert response.frames[0].verb == "web.click"
        db.frames.find.assert_called_once_with({"user_id": "u_1", "session_id": {"$in": ["s1"]}})
    finally:
        get_settings.cache_clear()


async def test_live_suggestions_obey_policy_daily_cap(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    import app.routers.p1_api as api

    monkeypatch.setenv("STUB_MODE", "false")
    get_settings.cache_clear()
    db = MagicMock()
    db.policy.find_one = AsyncMock(
        return_value={"thresholds": {"max_suggestions_per_day": 1, "T_high": 0.82}, "rules": []}
    )
    db.suggestion_impressions.count_documents = AsyncMock(return_value=0)
    patterns = MagicMock()
    patterns.sort.return_value.to_list = AsyncMock(
        return_value=[
            {
                "_id": "p1",
                "title": "One",
                "signature": ["web.click"],
                "support": 3,
                "distinct_days": 3,
                "value": 8,
            },
            {
                "_id": "p2",
                "title": "Two",
                "signature": ["web.submit"],
                "support": 3,
                "distinct_days": 3,
                "value": 7,
            },
        ]
    )
    db.patterns.find.return_value = patterns
    tools_cursor = MagicMock()
    tools_cursor.to_list = AsyncMock(return_value=[])
    db.tools.find.return_value = tools_cursor
    db.suggestion_impressions.update_one = AsyncMock()
    monkeypatch.setattr(api, "get_db", lambda: db)
    monkeypatch.setattr(api, "embed", AsyncMock(return_value=[[1.0, 0.0]]))
    try:
        response = await api.suggestions()
        assert [item["pattern_id"] for item in response] == ["p1"]
        db.suggestion_impressions.update_one.assert_awaited_once()
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("mutation", ["user", "raw_value", "bad_image", "duplicate_frame", "time"])
def test_capture_rejects_invalid_payload(client, mutation):
    batch = fixture("capture_batch.json")
    if mutation == "user":
        batch["events"][0]["user_id"] = "another_user"
    elif mutation == "raw_value":
        batch["events"][1]["value_shape"]["value"] = "secret text"
    elif mutation == "bad_image":
        batch["frames"][0]["image_webp_b64"] = base64.b64encode(b"not an image").decode()
    elif mutation == "duplicate_frame":
        batch["frames"][1]["client_id"] = batch["frames"][0]["client_id"]
    else:
        batch["events"][0]["ts"] = "2026-09-26T12:00:00"
    assert client.post("/capture/batch", json=batch).status_code == 422


def test_capture_rejects_other_user(client):
    batch = fixture("capture_batch.json")
    batch["user_id"] = "another_user"
    assert client.post("/capture/batch", json=batch).status_code == 403


def test_why_and_thumbnail(client):
    response = client.get("/suggestions/pat_uc1/why")
    assert response.status_code == 200
    frames = response.json()["frames"]
    assert len({item["ts"][:10] for item in frames}) == 3
    thumb = client.get(frames[0]["thumb_url"])
    assert thumb.headers["content-type"] == "image/webp"
    assert Image.open(BytesIO(thumb.content)).size[0] == 256
    assert client.get("/frames/unknown/thumb").status_code == 404


def test_live_mode_never_returns_fixtures(client, monkeypatch):
    import app.routers.p1_api as p1_api

    monkeypatch.setenv("STUB_MODE", "false")
    monkeypatch.setattr(
        p1_api, "get_db", lambda: (_ for _ in ()).throw(NotImplementedError("live store required"))
    )
    get_settings.cache_clear()
    assert client.get("/tools").status_code == 501


def test_confirm_does_not_execute_fixture(client):
    response = client.post("/tools/tool_uc1/run", json={"params": {}, "confirm": True})
    assert response.status_code == 200
    assert response.json()["mode"] == "dry_run"
    assert response.json()["needs_confirm"] is True


def test_low_confidence_needs_review():
    label = FrameLabel(verb="table.pivot", confidence=0.4, source="vlm", needs_review=False)
    assert label.needs_review
    with pytest.raises(ValidationError):
        FrameLabel(verb="table.pivot", confidence=1.5, source="vlm")


def test_p2_router_auto_discovery(tmp_path, monkeypatch):
    import app.routers

    path = tmp_path / "p2_probe.py"
    path.write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\n"
        "@router.get('/probe')\nasync def probe(): return {'ok': True}\n"
    )
    monkeypatch.setattr(app.routers, "__path__", [str(tmp_path)])
    application = FastAPI()
    discover_routers(application)
    with TestClient(application) as client:
        assert client.get("/probe").json() == {"ok": True}


async def test_registry_dispatch_and_discovery(tmp_path, monkeypatch):
    import app
    import worker

    (tmp_path / "probe").mkdir()
    (tmp_path / "probe/__init__.py").write_text("")
    (tmp_path / "probe/jobs.py").write_text(
        "from worker import register\nasync def handler(payload): return payload['value'] * 2\n"
        "register('probe', handler)\n"
    )
    monkeypatch.setattr(app, "__path__", [str(tmp_path)])
    monkeypatch.setattr(worker, "_handlers", {})
    assert worker.discover_jobs() == ["app.probe.jobs"]
    assert await worker.dispatch("probe", {"value": 3}) == 6
    with pytest.raises(LookupError):
        await worker.dispatch("unknown", {})


async def test_sse_publish_and_cleanup():
    stream = subscribe("u_1")
    assert "fixture" in await anext(stream)
    await publish("u_1", "frame_labeled", {"frame_id": "f_1"})
    chunk = await asyncio.wait_for(anext(stream), timeout=1)
    assert "event: frame_labeled" in chunk
    assert json.loads(chunk.split("data: ")[1])["data"] == {"frame_id": "f_1"}
    await stream.aclose()


async def test_atlas_event_publish_and_sse_are_user_scoped(monkeypatch):
    from datetime import datetime, timezone
    from types import SimpleNamespace

    import app.events as event_service

    class ChangeStream:
        def __init__(self):
            self.sent = False
            self.wait_forever = asyncio.Event()
            self.resume_token = {"_data": "resume"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.sent:
                self.sent = True
                return {
                    "fullDocument": {
                        "type": "policy_changed",
                        "ts": datetime.now(timezone.utc),
                        "user_id": "tenant-1",
                        "data": {"field": "min_support"},
                    }
                }
            await self.wait_forever.wait()
            raise StopAsyncIteration

    inserted = []
    watches = []
    changes = ChangeStream()

    async def insert_one(document):
        inserted.append(document)

    async def watch(pipeline, **options):
        watches.append((pipeline, options))
        return changes

    db = SimpleNamespace(events=SimpleNamespace(insert_one=insert_one, watch=watch))
    monkeypatch.setattr(event_service, "get_settings", lambda: SimpleNamespace(stub_mode=False))
    monkeypatch.setattr(event_service, "get_db", lambda: db)

    await event_service.publish("tenant-1", "policy_changed", {"field": "min_support"})
    stream = event_service.subscribe("tenant-1")
    assert "connected" in await anext(stream)
    chunk = await asyncio.wait_for(anext(stream), timeout=1)
    await stream.aclose()

    assert inserted[0]["user_id"] == "tenant-1"
    assert "event: policy_changed" in chunk
    assert json.loads(chunk.split("data: ")[1])["data"] == {"field": "min_support"}
    assert watches[0][0][0]["$match"]["fullDocument.user_id"] == "tenant-1"


async def test_database_initialization_is_repeatable():
    # Offline contract check only; live Atlas validation is tracked separately.
    collections = {}
    names = set()

    def collection(name):
        if name not in collections:
            collections[name] = MagicMock(create_index=AsyncMock(), update_one=AsyncMock())
        return collections[name]

    async def create(name, **kwargs):
        assert name not in names
        names.add(name)

    db = MagicMock()
    db.list_collection_names = AsyncMock(side_effect=lambda: list(names))
    db.create_collection = AsyncMock(side_effect=create)
    db.__getitem__.side_effect = collection
    for name in ["patterns", "tools", "runs", "frames", "ui_events", "action_vocab"]:
        setattr(db, name, collection(name))
    await initialize_database(db)
    count = db.create_collection.await_count
    await initialize_database(db)
    assert db.create_collection.await_count == count
    collection("frames").create_index.assert_any_await("expires_at", expireAfterSeconds=0)
    creation = next(
        call for call in db.create_collection.await_args_list if call.args == ("observations",)
    )
    assert creation.kwargs["timeseries"]["metaField"] == "meta"
    assert creation.kwargs["expireAfterSeconds"] == 5184000
    assert "timeseries" not in next(
        call.kwargs for call in db.create_collection.await_args_list if call.args == ("frames",)
    )
    assert db.action_vocab.update_one.await_count == 76  # 38 verbs x 2 runs (+ automation verbs)


@pytest.mark.parametrize(
    "module",
    [
        "llm",
        "embeddings",
        "sandbox.runner",
        "forge.service",
        "gate.service",
        "trust.service",
        "interpreter.service",
        "baseline.service",
        "concierge.service",
        "runtime.lineage",
    ],
)
def test_teammate_stubs_import(module):
    importlib.import_module(f"app.{module}")
