import asyncio

from pymongo.errors import OperationFailure

from app.config import get_settings
from app.contracts import EpisodeHit, ToolHit
from app.db import get_db
from app.embeddings import embed
from app.fixtures import fixture, require_demo_user

RRF_K = 60
SEARCH_LIMIT_FACTOR = 5


def _limit(k: int) -> int:
    return max(0, min(k, 100))


def _tool_pipelines(user_id: str, query_vector: list[float], query: str, per_pipeline: int):
    vector_pipeline = [
        {
            "$vectorSearch": {
                "index": "tools_vec",
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": max(per_pipeline * 10, 100),
                "limit": per_pipeline,
                "filter": {"user_id": user_id, "status": "active"},
            }
        }
    ]
    text_pipeline = [
        {
            "$search": {
                "index": "tools_text",
                "compound": {
                    "must": [
                        {
                            "text": {
                                "query": query,
                                "path": ["title", "name", "tutorial_md", "keywords"],
                            }
                        }
                    ],
                    "filter": [
                        {"equals": {"path": "user_id", "value": user_id}},
                        {"equals": {"path": "status", "value": "active"}},
                    ],
                },
            }
        },
        {"$limit": per_pipeline},
    ]
    return vector_pipeline, text_pipeline


async def _rank_fusion_tools(db, user_id: str, query_vector: list[float], query: str, k: int):
    per_pipeline = max(k * SEARCH_LIMIT_FACTOR, 20)
    vector_pipeline, text_pipeline = _tool_pipelines(user_id, query_vector, query, per_pipeline)
    pipeline = [
        {
            "$rankFusion": {
                "input": {"pipelines": {"vector": vector_pipeline, "text": text_pipeline}}
            }
        },
        {"$project": {"tool_id": 1, "name": 1, "score": {"$meta": "score"}}},
        {"$limit": k},
    ]
    return await (await db.tools.aggregate(pipeline)).to_list(length=k)


async def _rrf_fallback_tools(db, user_id: str, query_vector: list[float], query: str, k: int):
    per_pipeline = max(k * SEARCH_LIMIT_FACTOR, 20)
    vector_pipeline, text_pipeline = _tool_pipelines(user_id, query_vector, query, per_pipeline)
    vector_rows, text_rows = await asyncio.gather(
        (await db.tools.aggregate(vector_pipeline)).to_list(length=per_pipeline),
        (await db.tools.aggregate(text_pipeline)).to_list(length=per_pipeline),
    )
    scores = {}
    documents = {}
    for rows in (vector_rows, text_rows):
        for rank, row in enumerate(rows, start=1):
            tool_id = row.get("tool_id", row.get("_id"))
            if tool_id is None:
                continue
            key = str(tool_id)
            documents[key] = row
            scores[key] = scores.get(key, 0.0) + 1 / (RRF_K + rank)
    ranked = sorted(scores, key=scores.get, reverse=True)[:k]
    return [
        {"tool_id": key, "name": documents[key].get("name", ""), "score": scores[key]}
        for key in ranked
    ]


async def search_tools(user_id: str, query: str, k: int = 5) -> list[ToolHit]:
    k = _limit(k)
    if k == 0 or not query.strip():
        return []
    if get_settings().stub_mode:
        require_demo_user(user_id)
        tool = fixture("tool_uc1.json")
        return [ToolHit(tool_id=tool["tool_id"], name=tool["name"], score=1)][:k]
    if not user_id:
        raise ValueError("user_id is required")

    vectors = await embed([query], input_type="query")
    if len(vectors) != 1 or not vectors[0]:
        raise ValueError("Embedding service returned no query vector")
    db = get_db()
    try:
        rows = await _rank_fusion_tools(db, user_id, vectors[0], query, k)
    except OperationFailure:
        rows = await _rrf_fallback_tools(db, user_id, vectors[0], query, k)
    return [
        ToolHit(
            tool_id=str(row.get("tool_id", row.get("_id"))),
            name=row["name"],
            score=row["score"],
        )
        for row in rows
        if row.get("tool_id", row.get("_id")) is not None and row.get("name") is not None
    ]


async def recall_episodes(
    user_id: str,
    query: str,
    k: int = 5,
    signature: list[str] | None = None,
) -> list[EpisodeHit]:
    k = _limit(k)
    if k == 0 or (not query.strip() and not signature):
        return []
    if get_settings().stub_mode:
        require_demo_user(user_id)
        return [EpisodeHit(**item) for item in fixture("why_uc1.json")["episodes"]][:k]
    if not user_id:
        raise ValueError("user_id is required")

    db = get_db()
    rows = []
    if signature:
        signature_pipeline = [
            {"$match": {"user_id": user_id, "signature_seq": signature}},
            {"$sort": {"started_at": -1}},
            {"$limit": k},
            {
                "$project": {
                    "_id": 0,
                    "session_id": {"$toString": "$_id"},
                    "date": "$started_at",
                    "intent_summary": 1,
                    "minutes": 1,
                    "tokens": 1,
                    "score": {"$literal": 1.0},
                }
            },
        ]
        rows.extend(await (await db.sessions.aggregate(signature_pipeline)).to_list(length=k))

    if query.strip():
        vectors = await embed([query], input_type="query")
        if len(vectors) != 1 or not vectors[0]:
            raise ValueError("Embedding service returned no query vector")
        vector_pipeline = [
            {
                "$vectorSearch": {
                    "index": "sessions_vec",
                    "path": "intent_embedding",
                    "queryVector": vectors[0],
                    "numCandidates": max(k * 20, 100),
                    "limit": k,
                    "filter": {"user_id": user_id},
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "session_id": {"$toString": "$_id"},
                    "date": "$started_at",
                    "intent_summary": 1,
                    "minutes": 1,
                    "tokens": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
        rows.extend(await (await db.sessions.aggregate(vector_pipeline)).to_list(length=k))

    hits = {}
    for row in rows:
        hit = EpisodeHit(**row)
        if hit.session_id not in hits or hit.score > hits[hit.session_id].score:
            hits[hit.session_id] = hit
    return sorted(hits.values(), key=lambda hit: hit.score, reverse=True)[:k]
