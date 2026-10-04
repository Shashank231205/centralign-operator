"""Company memory service: what the operator has learned at this company across runs."""

import uuid

from app.domain.enums import MemoryKind
from app.infrastructure.db.engine import Database
from app.infrastructure.repositories.memory import MemoryRepository


class PostgresCompanyMemory:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def recall(self, query: str, limit: int) -> list[str]:
        async with self._database.session() as session:
            rows = await MemoryRepository(session).search(query, limit)
            return [f"[{row.kind}] {row.content}" for row in rows]

    async def learn(self, lessons: list[str], source_run: str) -> list[str]:
        return await self._add(MemoryKind.LESSON, lessons, source_run)

    async def remember_feedback(self, feedback: str, source_run: str) -> list[str]:
        return await self._add(MemoryKind.FEEDBACK, [feedback], source_run)

    async def _add(self, kind: MemoryKind, contents: list[str], source_run: str) -> list[str]:
        async with self._database.session() as session:
            return await MemoryRepository(session).add(kind, contents, uuid.UUID(source_run))
