"""Persistence boundary for Phase 1. Memory mode is explicitly opt-in via STUB_MODE."""

import json
from copy import deepcopy

from app.config import ROOT, get_settings
from app.contracts import Observation, Session
from app.db import get_db


class MemoryStore:
    def __init__(self):
        self.events = {}
        self.sessions = {}
        self.patterns = {}
        self.policies = {}

    async def observations(self, user_id):
        return deepcopy(self.events.get(user_id, []))

    async def insert_observations(self, user_id, events):
        self.events.setdefault(user_id, []).extend(deepcopy(events))

    async def save_sessions(self, user_id, sessions):
        self.sessions[user_id] = deepcopy(sessions)

    async def list_sessions(self, user_id):
        return deepcopy(self.sessions.get(user_id, []))

    async def save_patterns(self, user_id, patterns):
        existing = {p.id: p for p in self.patterns.get(user_id, [])}
        for pattern in patterns:
            old = existing.get(pattern.id)
            if old and (old.status in ("accepted", "toolified") or old.cooldown_until):
                continue
            existing[pattern.id] = deepcopy(pattern)
        self.patterns[user_id] = list(existing.values())

    async def vocabulary(self):
        return json.loads((ROOT / "data/action_vocab_seed.json").read_text())

    async def users_with_open_sessions(self):
        return [
            user for user, rows in self.sessions.items() if any(s.status == "open" for s in rows)
        ]

    async def ensure_policy(self, user_id, policy):
        return deepcopy(self.policies.setdefault(user_id, policy))


class MongoStore:
    def __init__(self, db=None):
        self.db = db if db is not None else get_db()

    async def observations(self, user_id):
        rows = (
            await self.db.observations.find({"meta.user_id": user_id}, {"_id": 0})
            .sort("ts", 1)
            .to_list(length=None)
        )
        return [Observation.model_validate(row) for row in rows]

    async def insert_observations(self, user_id, events):
        if events:
            await self.db.observations.insert_many([e.model_dump() for e in events])

    async def save_sessions(self, user_id, sessions):
        for session in sessions:
            await self.db.sessions.replace_one(
                {"_id": session.id, "user_id": user_id},
                session.model_dump(by_alias=True),
                upsert=True,
            )

    async def list_sessions(self, user_id):
        rows = await self.db.sessions.find({"user_id": user_id}).to_list(length=None)
        return [Session.model_validate(row) for row in rows]

    async def save_patterns(self, user_id, patterns):
        for pattern in patterns:
            # Never overwrite user decisions or promoted tools when mining again.
            existing = await self.db.patterns.find_one({"_id": pattern.id, "user_id": user_id})
            if existing and (
                existing["status"] in ("accepted", "toolified") or existing.get("cooldown_until")
            ):
                continue
            await self.db.patterns.replace_one(
                {"_id": pattern.id, "user_id": user_id},
                pattern.model_dump(by_alias=True),
                upsert=True,
            )

    async def ensure_policy(self, user_id, policy):
        await self.db.policy.update_one(
            {"_id": policy["_id"]}, {"$setOnInsert": policy}, upsert=True
        )
        return await self.db.policy.find_one({"_id": policy["_id"]})

    async def vocabulary(self):
        return await self.db.action_vocab.find({"status": "active"}).to_list(length=None)

    async def users_with_open_sessions(self):
        return await self.db.sessions.distinct("user_id", {"status": "open"})


memory_store = MemoryStore()


def get_store():
    return memory_store if get_settings().stub_mode else MongoStore()
