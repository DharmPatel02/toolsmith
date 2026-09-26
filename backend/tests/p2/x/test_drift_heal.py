"""P2.3.1 drift -> heal job; P2.3.2 heal: flip to v2 -> fails -> healed version passes v1 and v2."""
from datetime import UTC, datetime, timedelta

import pytest
from mongomock_motor import AsyncMongoMockClient

from app import llm
from app.forge import deps
from app.trust import drift, heal, jobs, promote, uc3_seed
from tests.p2.c.test_promote import staging_txn

HEALED_CODE = '''\
from bs4 import BeautifulSoup


def run(ctx, url):
    soup = BeautifulSoup(ctx.fetch(url), "html.parser")
    rows = []
    for item in soup.select("li.product, article.card"):
        name = item.select_one(".product-name, .card-title").get_text(strip=True)
        price = item.select_one(".price, .card-price").get_text(strip=True)
        rows.append({"name": name, "price": round(float(price.replace("$", "").replace(",", "")), 2)})
    if not rows:
        raise ValueError("no products found on the page")
    rows.sort(key=lambda r: r["name"])
    cheapest = min(rows, key=lambda r: r["price"])
    return {"summary": f"{len(rows)} products, cheapest {cheapest['name']} at ${cheapest['price']:.2f}",
            "tables": {"products": rows}}
'''
HEALED_TESTS = uc3_seed.UC3_V1_TESTS + '''

def test_v2_layout():
    page = '<article class="card"><div class="card-price">$3.00</div><h3 class="card-title">C</h3></article>'
    assert run(FakeCtx(pages={"u": page}), url="u")["tables"]["products"] == [{"name": "C", "price": 3.0}]
'''


class FakeHeavy:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0

    async def complete(self, tier, messages, json_schema=None, **kw):
        assert tier == "heavy" and "diagnosis" in json_schema["required"]
        self.calls += 1
        code, tests = self.answers.pop(0)
        return llm.LLMResult(text="", json={"diagnosis": "`.price` became `.card-price`, `li.product` became "
                                                         "`article.card`", "code": code, "tests": tests},
                             tokens_in=900, tokens_out=400, usd=0.01)


@pytest.fixture
def env(monkeypatch):
    db = AsyncMongoMockClient()["heal_test"]
    deps.use_db(db)
    events = []

    async def pub(u, t, d):
        events.append((t, d))
    deps.use_publisher(pub)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.setenv("MOCKSITE_URL", "http://127.0.0.1:9")  # nothing listens: capture falls back to v2
    monkeypatch.setattr(uc3_seed, "SNAPSHOT_DIR", uc3_seed.SNAPSHOT_DIR / "__none__")
    monkeypatch.setattr(promote, "_run_in_transaction", staging_txn)
    yield db, events, monkeypatch
    deps.use_db(None)
    deps.use_publisher(None)


async def _fail_runs(db, n, start=100):
    now = datetime.now(UTC)
    await db.runs.insert_many([{"_id": f"run_fail_{start + i}","tool_id": uc3_seed.TOOL_ID, "user_id": "u_1",
                                "params": {"url": uc3_seed.shop_url()}, "outcome": "failed", "ok": False,
                                "error": "AttributeError: 'NoneType' object has no attribute 'get_text'",
                                "started_at": now + timedelta(seconds=start + i)} for i in range(n)])


@pytest.mark.asyncio
async def test_seed_is_idempotent_and_v1_fixture_is_real(env):
    db, _, _ = env
    await uc3_seed.seed_uc3_tool("u_1")
    await uc3_seed.seed_uc3_tool("u_1")
    assert await db.tools.count_documents({}) == 1 and await db.runs.count_documents({}) == 12
    tv = await db.tool_versions.find_one({"_id": "tool_uc3_prices@v1"})
    rows = tv["fixtures_ref"]["replay_cases"][0]["expected"]["tables"]["products"]
    assert len(rows) == 6 and rows[0] == {"name": "Desk Lamp", "price": 24.99}
    assert tv["requires"]["scopes"] == ["net:127.0.0.1"]


@pytest.mark.asyncio
async def test_three_failures_queue_one_heal_job(env):
    db, events, _ = env
    await uc3_seed.seed_uc3_tool("u_1")
    assert await drift.check_drift(uc3_seed.TOOL_ID) is False
    await _fail_runs(db, 2)
    assert await drift.check_drift(uc3_seed.TOOL_ID) is False
    await _fail_runs(db, 1, start=200)
    assert await drift.check_drift(uc3_seed.TOOL_ID) is True
    assert await drift.check_drift(uc3_seed.TOOL_ID) is True          # still drifting, no second job
    job = await db.jobs.find_one({"type": "heal"})
    assert await db.jobs.count_documents({"type": "heal"}) == 1
    assert job["payload"]["tool_id"] == uc3_seed.TOOL_ID and len(job["payload"]["failing_run_ids"]) == 3
    assert [t for t, _ in events] == ["drift_detected"]


def test_rate_drop():
    runs = [{"outcome": "success"}] * 4 + [{"outcome": "failed"}, {"outcome": "success"}] * 3
    assert drift.assess(runs, 1.0) is None                              # 70 % vs 100 %: within 0.3
    runs = [{"outcome": "failed"}, {"outcome": "success"}] * 5
    assert drift.assess(runs, 1.0)["kind"] == "rate_drop"


@pytest.mark.asyncio
async def test_heal_flip_to_v2(env):
    db, events, mp = env
    await uc3_seed.seed_uc3_tool("u_1")
    await _fail_runs(db, 3)
    await drift.check_drift(uc3_seed.TOOL_ID)
    job = await db.jobs.find_one({"type": "heal"})
    # first answer is still brittle (v1 selectors only) -> gate fails on v2 -> second answer passes
    fake = FakeHeavy([(uc3_seed.UC3_V1_CODE, uc3_seed.UC3_V1_TESTS), (HEALED_CODE, HEALED_TESTS)])
    mp.setattr(heal.llm, "complete", fake.complete)
    out = await jobs.handle_heal(job)

    assert out["status"] == "healed" and out["version"] == 2 and fake.calls == 2
    assert out["page_source"] == "snapshot" and out["time_to_heal_ms"] >= 0
    tool = await db.tools.find_one({"_id": uc3_seed.TOOL_ID})
    assert tool["active_version"] == 2 and tool["trust"] == "dry_run" and tool["drift"]["active"] is False
    tv2 = await db.tool_versions.find_one({"_id": "tool_uc3_prices@v2"})
    assert tv2["code"] == HEALED_CODE
    labels = [c["label"] for c in tv2["fixtures_ref"]["replay_cases"]]
    assert labels[0] == "mocksite_v1" and labels[1].startswith("heal_")   # v2 page is now a fixture too
    verdict = await db.verdicts.find_one({"_id": (await db.candidates.find_one({"_id": out["candidate_id"]}))
                                          ["verdict_id"]})
    assert verdict["decision"] == "passed" and all(c["ok"] for c in verdict["checks"]["replay"]["cases"])
    types = [t for t, _ in events]
    assert types.index("drift_detected") < types.index("gate_failed") < types.index("gate_passed") \
        < types.index("promoted") < types.index("healed")


@pytest.mark.asyncio
async def test_heal_not_reproduced_when_page_still_v1(env):
    db, _, mp = env
    await uc3_seed.seed_uc3_tool("u_1")

    async def v1_page(url, tool_id):
        return uc3_seed.snapshot("v1"), "live"
    mp.setattr(heal, "capture_page", v1_page)

    async def no_llm(*a, **k):
        raise AssertionError("no model call when nothing is broken")
    mp.setattr(heal.llm, "complete", no_llm)
    out = await heal.heal_tool(uc3_seed.TOOL_ID)
    assert out["status"] == "not_reproduced"
    assert (await db.tools.find_one({"_id": uc3_seed.TOOL_ID}))["active_version"] == 1
