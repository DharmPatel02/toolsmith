import itertools
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from app.config import ROOT, get_settings
from app.contracts import Observation, ObservationBatch
from app.ingest.normalize import normalize
from app.ingest.service import close_idle, ingest
from app.ingest.store import MemoryStore, memory_store
from app.main import app
from app.miner.features import cluster_intents, sequence_variance, window_stats
from app.miner.prefixspan import mine_sequences
from app.miner.service import mine_user
from app.miner.signatures import to_signature
from fastapi.testclient import TestClient

from data.generator import generate, write_history
from scripts.seed import load_events, seed

NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fixture_mode(monkeypatch):
    monkeypatch.setenv("STUB_MODE", "true")
    monkeypatch.setenv("DEMO_USER_ID", "u_1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def embed(texts):
    return [[1.0, 0.1] for _ in texts]


def event(ts, *, session_id=None):
    return Observation(
        ts=ts,
        meta={"user_id": "u_1", "source": "pandas"},
        session_id=session_id,
        action="pivot_table",
        signature="legacy.pivot",
        args_shape={"rows": "Region", "values": "Amount"},
        intent_text="Make weekly sales dashboard",
        duration_ms=60000,
        cost={"tokens": 30},
    )


def test_canonical_signatures(caplog):
    assert (
        to_signature("insert pivottable", {})
        == to_signature("pandas.pivot_table", {})
        == "table.pivot:2col"
    )
    assert to_signature("pandas.read_excel", {}) == "file.open:xlsx"
    assert to_signature("web.submit", {}) == "web.submit:form"
    assert to_signature("unknown_test_verb", {}) == "other"
    assert "Unknown action" in caplog.text


def test_redaction_and_review():
    row = event(NOW)
    row.intent_text = "Email alice@example.com token=abc123 sk-abcdefghijk"
    row.args_shape["api_key"] = "secret"
    row.target["name"] = "alice@example.com"
    row.evidence.ocr_snippet = "Bearer abc.def.ghi"
    row.evidence.confidence = 0.4
    result = normalize(row)
    encoded = result.model_dump_json()
    assert all(
        secret not in encoded
        for secret in ["alice@example.com", "abc123", "sk-abcdefghijk", "abc.def.ghi"]
    )
    assert result.args_shape["api_key"] == "<REDACTED>"
    assert result.signature == "table.pivot:2col"
    assert result.meta.source == "pandas"
    assert result.evidence.needs_review


async def test_batch_and_live_sessionization():
    store = MemoryStore()
    first = NOW - timedelta(hours=3)
    await ingest(
        ObservationBatch(user_id="u_1", events=[event(first)]), store=store, embed=embed, now=first
    )
    await ingest(
        ObservationBatch(user_id="u_1", events=[event(first + timedelta(minutes=1))]),
        store=store,
        embed=embed,
        now=first + timedelta(minutes=1),
    )
    assert len(await store.list_sessions("u_1")) == 1
    assert (await store.list_sessions("u_1"))[0].status == "open"
    await ingest(
        ObservationBatch(user_id="u_1", events=[event(first + timedelta(hours=1))]),
        store=store,
        embed=embed,
        now=NOW,
    )
    sessions = await store.list_sessions("u_1")
    assert len(sessions) == 2
    assert all(s.status == "closed" and s.intent_embedding for s in sessions)
    assert sum(s.tokens for s in sessions) == 90
    assert await close_idle("u_1", store=store, embed=embed, now=NOW) == []


async def test_live_idle_closure_without_new_events():
    store = MemoryStore()
    await ingest(
        ObservationBatch(user_id="u_1", events=[event(NOW)]), store=store, embed=embed, now=NOW
    )
    assert (
        len(await close_idle("u_1", store=store, embed=embed, now=NOW + timedelta(minutes=31))) == 1
    )


def test_prefixspan_bounded_gap_and_unique_session_support():
    sequences = [["a", "noise", "b", "c"], ["a", "b", "c"], ["a", "b", "c", "a", "b", "c"]]
    found = {p.signature: p.support for p in mine_sequences(sequences, max_gap=1)}
    assert found[("a", "b", "c")] == 3
    assert not mine_sequences(sequences, max_gap=0)
    assert not mine_sequences([["a", "b", "c"] * 6], min_support=3)
    # The later occurrence of 'a' must not be lost during projection.
    assert mine_sequences([["a", "x", "x", "a", "b", "c"]] * 3, max_gap=0)


def test_prefixspan_matches_bruteforce():
    sequences = [list("abacb"), list("bacab"), list("ababc")]
    expected = {}
    for sid, sequence in enumerate(sequences):
        for length in (3, 4):
            for indexes in itertools.combinations(range(len(sequence)), length):
                if all(b - a <= 2 for a, b in zip(indexes, indexes[1:])):
                    signature = tuple(sequence[i] for i in indexes)
                    expected.setdefault(signature, set()).add(sid)
    expected = {sig: tuple(sorted(ids)) for sig, ids in expected.items() if len(ids) >= 2}
    actual = {
        p.signature: p.session_indexes
        for p in mine_sequences(sequences, min_support=2, max_length=4, max_gap=1)
    }
    assert actual == expected


def test_window_features_and_clustering():
    weekly = window_stats([NOW - timedelta(days=d) for d in (0, 7, 14)])
    assert weekly["periodicity"] == 1 and weekly["distinct_days"] == 3
    assert window_stats([NOW + timedelta(minutes=n) for n in range(6)])["burstiness"] >= 0.8
    assert sequence_variance([list("abc"), list("xyz")]) == 1
    labels = cluster_intents([[1.0, 0.0], [0.99, 0.01], [0.0, 1.0]])
    assert labels[0] == labels[1] != labels[2]
    with pytest.raises(ValueError):
        cluster_intents([[0.0, 0.0]])


def test_generator_counts_dates_and_determinism(tmp_path):
    full, logs, truth = generate()
    assert (len(full), len(logs), len(truth["sessions"])) == (1000, 979, 40)
    assert generate() == (full, logs, truth)
    assert all(
        datetime.fromisoformat(s["started_at"]).weekday() == 0
        for s in truth["sessions"]
        if s["workflow"] == "uc1"
    )
    assert len({s["started_at"][:10] for s in truth["sessions"] if s["workflow"] == "decoy_a"}) == 1
    assert not any(e["evidence"]["tier"] == "T2" for e in logs)
    for row in full:
        Observation.model_validate(row)
    write_history(tmp_path)
    second = load_events(tmp_path, "u_1_logs_only", logs_only=True)
    assert all(e["meta"]["user_id"] == "u_1_logs_only" for e in second)
    assert all(e["session_id"].startswith("u_1_logs_only:") for e in second)


async def test_generated_pipeline_and_ablation():
    full, logs, truth = generate()
    store = MemoryStore()
    await ingest(ObservationBatch(user_id="u_1", events=full), store=store, embed=embed, now=NOW)
    patterns = await mine_user("u_1", store=store, now=NOW)
    groups = {
        label: {s["session_id"] for s in truth["sessions"] if s["workflow"] == label}
        for label in ("uc1", "uc2", "uc3", "decoy_a", "decoy_b", "noise")
    }
    for label in ("uc1", "uc2", "uc3"):
        assert any(
            p.status == "mined" and set(p.evidence_session_ids) == groups[label] for p in patterns
        ), label
    for label, reason in [("decoy_a", "one-day burst"), ("decoy_b", "high variance")]:
        assert any(
            p.declined_reason == reason and set(p.evidence_session_ids) == groups[label]
            for p in patterns
        ), label
    assert not any(
        p.status == "mined" and groups["noise"].intersection(p.evidence_session_ids)
        for p in patterns
    )
    uc1 = next(
        p for p in patterns if p.status == "mined" and set(p.evidence_session_ids) == groups["uc1"]
    )
    assert any(param.type == "file" for param in uc1.dynamic_params)
    assert any("rows" in name for name in uc1.static_steps)
    # Remove all screen observations. UC1 must vanish without consulting ground truth in the miner.
    other = MemoryStore()
    await ingest(ObservationBatch(user_id="u_1", events=logs), store=other, embed=embed, now=NOW)
    remaining = await mine_user("u_1", store=other, now=NOW)
    assert not any(
        p.status == "mined" and groups["uc1"].intersection(p.evidence_session_ids)
        for p in remaining
    )
    assert await store.list_sessions("different_user") == []


async def test_needs_review_steps_do_not_add_support():
    full, _, _ = generate()
    for row in full:
        if row["session_id"] == "u_1_uc1_3":
            row["evidence"]["needs_review"] = True
    store = MemoryStore()
    await ingest(ObservationBatch(user_id="u_1", events=full), store=store, embed=embed, now=NOW)
    patterns = await mine_user("u_1", store=store, now=NOW)
    assert not any(p.status == "mined" and "u_1_uc1_3" in p.evidence_session_ids for p in patterns)


async def test_seed_api_counts_and_isolation(tmp_path):
    write_history(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for user, logs in [("u_1", False), ("u_1_logs_only", True)]:
            response = await client.post("/dev/reset-history", json={"user_id": user})
            assert response.status_code == 200
            result = await seed(client, load_events(tmp_path, user, logs), user, batch_size=137)
            assert result["inserted"] == (979 if logs else 1000)
        assert len(await memory_store.observations("u_1")) == 1000
        assert len(await memory_store.observations("u_1_logs_only")) == 979
        assert (
            await client.post("/dev/reset-history", json={"user_id": "other"})
        ).status_code == 403
        await client.post("/dev/reset-history", json={"user_id": "u_1"})
        assert len(await memory_store.observations("u_1_logs_only")) == 979


def test_restored_phase0_capture_and_lineage():
    with TestClient(app) as client:
        try:
            assert client.post("/capture/pause").json() == {"ok": True}
            assert client.get("/capture/state").json()["paused"]
            response = client.post(
                "/capture/batch",
                json=json.loads((ROOT / "fixtures/capture_batch.json").read_text()),
            )
            assert response.json()["frames_kept"] == 0 and response.json()["paused"]
            assert len(client.get("/tools/tool_uc2/lineage").json()["calls"]) == 2
            assert client.post("/capture/delete_last?minutes=-1").status_code == 422
        finally:
            client.post("/capture/resume")


async def test_worker_closes_idle_sessions_and_reuses_embeddings():
    from unittest.mock import AsyncMock

    from worker import close_idle_sessions

    store = MemoryStore()
    provider = AsyncMock(side_effect=embed)
    await ingest(
        ObservationBatch(user_id="u_1", events=[event(NOW)]), store=store, embed=provider, now=NOW
    )
    assert provider.await_count == 0
    assert (
        len(await close_idle_sessions(store=store, embed=provider, now=NOW + timedelta(minutes=31)))
        == 1
    )
    assert provider.await_count == 1
    await close_idle("u_1", store=store, embed=provider, now=NOW + timedelta(hours=1))
    assert provider.await_count == 1


def test_ui_anchors_are_static_and_values_dynamic():
    from app.miner.features import split_parameters

    first, second = event(NOW), event(NOW + timedelta(days=7))
    first.target = second.target = {"role": "button", "name": "Export"}
    first.args_shape["file"] = "week1.xlsx"
    second.args_shape["file"] = "week2.xlsx"
    static, dynamic = split_parameters([[first], [second]])
    assert static["step_0.element.role"] == "button"
    assert static["step_0.element.name"] == "Export"
    assert {"name": "step_0.file", "type": "file"} in dynamic


async def test_mongo_adapter_keeps_user_filters_and_normalized_data():
    from unittest.mock import AsyncMock, MagicMock

    from app.ingest.store import MongoStore

    db = MagicMock()
    db.observations.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
    db.observations.insert_many = AsyncMock()
    store = MongoStore(db)
    assert await store.observations("u_1") == []
    db.observations.find.assert_called_once_with({"meta.user_id": "u_1"}, {"_id": 0})
    normalized = normalize(event(NOW))
    await store.insert_observations("u_1", [normalized])
    written = db.observations.insert_many.await_args.args[0][0]
    assert written["signature"] == "table.pivot:2col"
    assert written["meta"] == {"user_id": "u_1", "source": "pandas"}


async def test_search_index_budget_and_no_false_ready():
    from unittest.mock import AsyncMock, MagicMock

    from scripts.search_indexes import apply_indexes, index_plan

    plans = index_plan(frame_dims=1024)
    assert [p["name"] for p in plans] == [
        "tools_vec",
        "sessions_vec",
        "tools_text",
        "frames_vec",
        "patterns_vec",
    ]
    for plan in plans:
        if plan["type"] == "vectorSearch":
            assert {"type": "filter", "path": "user_id"} in plan["definition"]["fields"]
    db = MagicMock()
    collection = MagicMock()
    db.__getitem__.return_value = collection
    cursor = MagicMock()
    cursor.to_list = AsyncMock(side_effect=[[], [{"status": "READY"}]])
    collection.list_search_indexes = AsyncMock(return_value=cursor)
    collection.create_search_index = AsyncMock()
    report = await apply_indexes(db, plans, budget=1)
    assert report[0]["status"] == "READY"
    assert all(row["status"] == "SKIPPED" for row in report[1:])
    assert collection.create_search_index.await_count == 1
    cursor.to_list = AsyncMock(return_value=[])
    with pytest.raises(TimeoutError):
        await apply_indexes(db, plans, budget=1, timeout=0)


async def test_search_tools_uses_rank_fusion_and_tenant_filters(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app import search

    pipelines = []

    class Cursor:
        async def to_list(self, length):
            return [{"tool_id": "tool-1", "name": "Weekly report", "score": 0.04}]

    async def aggregate(pipeline):
        pipelines.append(pipeline)
        return Cursor()

    collection = SimpleNamespace(aggregate=aggregate)
    db = SimpleNamespace(tools=collection)
    monkeypatch.setattr(search, "get_settings", lambda: SimpleNamespace(stub_mode=False))
    monkeypatch.setattr(search, "embed", AsyncMock(return_value=[[0.1, 0.2]]))
    monkeypatch.setattr(search, "get_db", lambda: db)

    hits = await search.search_tools("tenant-1", "summarize weekly sales", k=3)

    assert hits[0].tool_id == "tool-1"
    assert hits[0].score == 0.04
    fusion = pipelines[0][0]["$rankFusion"]["input"]["pipelines"]
    vector = fusion["vector"][0]["$vectorSearch"]
    assert vector["filter"] == {"user_id": "tenant-1", "status": "active"}
    text_filter = fusion["text"][0]["$search"]["compound"]["filter"]
    assert text_filter == [
        {"equals": {"path": "user_id", "value": "tenant-1"}},
        {"equals": {"path": "status", "value": "active"}},
    ]


async def test_search_tools_falls_back_to_client_rrf(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app import search
    from pymongo.errors import OperationFailure

    calls = []

    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        async def to_list(self, length):
            return self.rows

    async def aggregate(pipeline):
        calls.append(pipeline)
        if len(calls) == 1:
            raise OperationFailure("$rankFusion is unavailable")
        if "$vectorSearch" in pipeline[0]:
            return Cursor(
                [
                    {"tool_id": "tool-b", "name": "B"},
                    {"tool_id": "tool-a", "name": "A"},
                ]
            )
        return Cursor(
            [
                {"tool_id": "tool-b", "name": "B"},
                {"tool_id": "tool-a", "name": "A"},
            ]
        )

    db = SimpleNamespace(tools=SimpleNamespace(aggregate=aggregate))
    monkeypatch.setattr(search, "get_settings", lambda: SimpleNamespace(stub_mode=False))
    monkeypatch.setattr(search, "embed", AsyncMock(return_value=[[0.1, 0.2]]))
    monkeypatch.setattr(search, "get_db", lambda: db)

    hits = await search.search_tools("tenant-1", "weekly report", k=2)

    assert [hit.tool_id for hit in hits] == ["tool-b", "tool-a"]
    assert len(calls) == 3
    assert calls[1][0]["$vectorSearch"]["filter"] == {
        "user_id": "tenant-1",
        "status": "active",
    }
    assert calls[2][0]["$search"]["compound"]["filter"] == [
        {"equals": {"path": "user_id", "value": "tenant-1"}},
        {"equals": {"path": "status", "value": "active"}},
    ]


async def test_recall_episodes_uses_scoped_vector_search(monkeypatch):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app import search

    calls = []

    class Cursor:
        async def to_list(self, length):
            return [
                {
                    "session_id": "session-1",
                    "date": datetime(2026, 9, 26, tzinfo=timezone.utc),
                    "intent_summary": "Weekly report",
                    "minutes": 12,
                    "tokens": 30,
                    "score": 0.9,
                }
            ]

    async def aggregate(pipeline):
        calls.append(pipeline)
        return Cursor()

    db = SimpleNamespace(sessions=SimpleNamespace(aggregate=aggregate))
    monkeypatch.setattr(search, "get_settings", lambda: SimpleNamespace(stub_mode=False))
    monkeypatch.setattr(search, "embed", AsyncMock(return_value=[[0.1, 0.2]]))
    monkeypatch.setattr(search, "get_db", lambda: db)

    hits = await search.recall_episodes("tenant-1", "weekly report", k=3)

    assert hits[0].session_id == "session-1"
    vector_stage = calls[0][0]["$vectorSearch"]
    assert vector_stage["index"] == "sessions_vec"
    assert vector_stage["filter"] == {"user_id": "tenant-1"}


async def test_recall_episodes_supports_exact_signature_sequences(monkeypatch):
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from app import search

    calls = []

    class Cursor:
        async def to_list(self, length):
            return [
                {
                    "session_id": "session-1",
                    "date": datetime(2026, 9, 26, tzinfo=timezone.utc),
                    "intent_summary": "Weekly report",
                    "minutes": 12,
                    "tokens": 30,
                    "score": 1.0,
                }
            ]

    async def aggregate(pipeline):
        calls.append(pipeline)
        return Cursor()

    db = SimpleNamespace(sessions=SimpleNamespace(aggregate=aggregate))
    monkeypatch.setattr(search, "get_settings", lambda: SimpleNamespace(stub_mode=False))
    monkeypatch.setattr(search, "get_db", lambda: db)

    hits = await search.recall_episodes(
        "tenant-1", "", k=3, signature=["file.open:xlsx", "table.pivot:2col"]
    )

    assert hits[0].session_id == "session-1"
    assert calls[0][0]["$match"] == {
        "user_id": "tenant-1",
        "signature_seq": ["file.open:xlsx", "table.pivot:2col"],
    }


async def test_reset_is_scoped_to_demo_user():
    from scripts.seed import reset_live_user

    with pytest.raises(ValueError, match="limited"):
        await reset_live_user("unrelated_customer")
