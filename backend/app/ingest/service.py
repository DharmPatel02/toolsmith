"""Ingest and close sessions using one path for offline tests and Atlas."""

from datetime import datetime, timezone
from hashlib import sha256

from app import embeddings
from app.config import get_settings
from app.contracts import ObservationBatch
from app.ingest.normalize import normalize
from app.ingest.sessionizer import IDLE, sessionize
from app.ingest.store import get_store
from app.miner.signatures import configure_vocab


async def ingest(batch: ObservationBatch, *, store=None, embed=None, now=None):
    store = store if store is not None else get_store()
    embed = embed or embeddings.embed
    configure_vocab(await store.vocabulary())
    normalized = [normalize(event) for event in batch.events]
    previous = await store.observations(batch.user_id)
    # Attach new unlabelled events to the preceding session across HTTP batches.
    last = None
    for event in sorted(previous + normalized, key=lambda item: item.ts):
        if event.session_id is None:
            event.session_id = (
                last.session_id
                if last and event.ts - last.ts < IDLE
                else "s_"
                + sha256(f"{batch.user_id}:{event.ts.isoformat()}".encode()).hexdigest()[:20]
            )
        last = event
    sessions = await sessionize(
        previous + normalized,
        embed,
        now=now,
        previous=await store.list_sessions(batch.user_id),
        embedding_model="fixture" if get_settings().stub_mode else get_settings().embed_model,
    )
    await store.insert_observations(batch.user_id, normalized)
    await store.save_sessions(batch.user_id, sessions)
    touched = {event.session_id for event in normalized}
    return {"inserted": len(normalized), "sessions_touched": len(touched)}


async def close_idle(user_id: str, *, store=None, embed=None, now=None):
    """Callable by the live worker timer even when no new event arrives."""
    store = store if store is not None else get_store()
    previous = await store.list_sessions(user_id)
    rows = await store.observations(user_id)
    sessions = await sessionize(
        rows,
        embed or embeddings.embed,
        now=now or datetime.now(timezone.utc),
        previous=previous,
        embedding_model="fixture" if get_settings().stub_mode else get_settings().embed_model,
    )
    await store.save_sessions(user_id, sessions)
    old_closed = {s.id for s in previous if s.status == "closed"}
    return [s.id for s in sessions if s.status == "closed" and s.id not in old_closed]
