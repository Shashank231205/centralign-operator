"""Use case: accept a natural-language request and queue it as a run (202 semantics)."""

import uuid
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from app.infrastructure.cache.coordination import IdempotencyCache
from app.infrastructure.db.engine import Database
from app.infrastructure.queue.jobs import RunQueue
from app.infrastructure.repositories.runs import RunRepository


@dataclass(frozen=True, slots=True)
class Accepted:
    run_id: uuid.UUID
    replayed: bool


class TaskService:
    def __init__(self, database: Database, queue: RunQueue, idempotency: IdempotencyCache) -> None:
        self._database = database
        self._queue = queue
        self._idempotency = idempotency

    async def submit(
        self, request: str, idempotency_key: str | None, api_key_id: uuid.UUID | None
    ) -> Accepted:
        if idempotency_key and (existing := await self._replay(idempotency_key)):
            return Accepted(existing, replayed=True)
        try:
            async with self._database.session() as session:
                state = await RunRepository(session).create(request, idempotency_key, api_key_id)
        except IntegrityError:
            # A concurrent request with the same key won the race; return its run.
            assert idempotency_key is not None
            existing = await self._replay(idempotency_key)
            if existing is None:
                raise
            return Accepted(existing, replayed=True)
        if idempotency_key:
            await self._idempotency.put(idempotency_key, state.run_id)
        await self._queue.enqueue(state.run_id)
        return Accepted(state.run_id, replayed=False)

    async def _replay(self, key: str) -> uuid.UUID | None:
        if cached := await self._idempotency.get(key):
            return cached
        async with self._database.session() as session:
            return await RunRepository(session).find_by_idempotency_key(key)
