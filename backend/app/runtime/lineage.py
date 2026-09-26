"""Tool dependency lineage for composed tools."""

from datetime import datetime, timezone
from inspect import isawaitable
from uuid import uuid4

from app.config import get_settings
from app.contracts import LineageNode, LineageResponse, ToolDep
from app.db import get_db
from app.fixtures import fixture, require_demo_user


async def resolve_deps(user_id: str, tool_id: str) -> list[ToolDep]:
    if get_settings().stub_mode:
        require_demo_user(user_id)
        if tool_id == "tool_uc2":
            return [
                ToolDep(**{k: v for k, v in row.items() if k != "depth"})
                for row in fixture("lineage_uc2.json")["calls"]
            ]
        return []
    response = await lineage(user_id, tool_id)
    tool = await get_db().tools.find_one(
        {"$or": [{"_id": tool_id}, {"tool_id": tool_id}], "user_id": user_id},
        {"lineage.calls": 1},
    )
    expected = set((tool or {}).get("lineage", {}).get("calls", []))
    resolved = {node.name for node in response.calls}
    if expected and not expected.issubset(resolved):
        await get_db().jobs.insert_one(
            {
                "_id": f"forge:{uuid4().hex}",
                "type": "forge",
                "payload": {
                    "user_id": user_id,
                    "tool_id": tool_id,
                    "reason": "missing_lineage_dependency",
                    "missing": sorted(expected - resolved),
                },
                "status": "queued",
                "created_at": datetime.now(timezone.utc),
            }
        )
        raise LookupError("Tool dependencies could not be resolved")
    return [ToolDep(**node.model_dump(exclude={"depth"})) for node in response.calls]


async def dependents(user_id: str, tool_id: str) -> list[str]:
    if get_settings().stub_mode:
        require_demo_user(user_id)
        return []
    tool = await get_db().tools.find_one(
        {"$or": [{"_id": tool_id}, {"tool_id": tool_id}], "user_id": user_id},
        {"name": 1},
    )
    names = [tool_id]
    if tool and tool.get("name"):
        names.append(tool["name"])
    rows = await get_db().tools.find(
        {"user_id": user_id, "status": "active", "lineage.calls": {"$in": names}},
        {"_id": 1, "tool_id": 1},
    ).to_list(length=None)
    return [str(row.get("tool_id") or row["_id"]) for row in rows]


async def lineage(user_id: str, tool_id: str) -> LineageResponse:
    if get_settings().stub_mode:
        require_demo_user(user_id)
        if tool_id == "tool_uc2":
            return LineageResponse(**fixture("lineage_uc2.json"))
        if tool_id == "tool_uc1":
            return LineageResponse(calls=[], merged_from=[], merged_into=None, dependents=[])
        raise LookupError("Unknown fixture tool")
    db = get_db()
    pipeline = [
        {
            "$match": {
                "$or": [{"_id": tool_id}, {"tool_id": tool_id}],
                "user_id": user_id,
                "status": "active",
            }
        },
        {
            "$graphLookup": {
                "from": "tools",
                "startWith": "$lineage.calls",
                "connectFromField": "lineage.calls",
                "connectToField": "name",
                "as": "deps",
                "maxDepth": 4,
                "depthField": "depth",
                "restrictSearchWithMatch": {"user_id": user_id, "status": "active"},
            }
        },
        {"$limit": 1},
    ]
    cursor = db.tools.aggregate(pipeline)
    if isawaitable(cursor):
        cursor = await cursor
    rows = await cursor.to_list(length=1)
    if not rows:
        raise LookupError("Unknown tool")
    tool = rows[0]
    calls = []
    for dep in tool.get("deps", []):
        version = dep.get("version") or {}
        calls.append(
            LineageNode(
                tool_id=str(dep.get("tool_id") or dep.get("_id")),
                name=dep.get("name", ""),
                version=dep.get("active_version", version.get("version", 1)),
                code=version.get("code", ""),
                depth=dep.get("depth", 0),
            )
        )
    return LineageResponse(
        calls=calls,
        merged_from=tool.get("lineage", {}).get("merged_from", []),
        merged_into=tool.get("lineage", {}).get("merged_into"),
        dependents=await dependents(user_id, tool_id),
    )
