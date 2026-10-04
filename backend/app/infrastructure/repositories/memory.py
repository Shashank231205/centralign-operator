"""Long-term company memory in Postgres, retrieved with full-text search (GIN index).

Full-text ranking is deterministic and explainable for short lessons; the repository interface
would accept a vector index later without touching the runtime.
"""

import hashlib
import re
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import MemoryKind
from app.infrastructure.db.models import MemoryEntryRow

_TERM = re.compile(r"[a-z0-9]{3,}")
_TS_CONFIG = "english"


def content_hash(content: str) -> str:
    normalised = " ".join(content.lower().split())
    return hashlib.sha256(normalised.encode()).hexdigest()


class MemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(self, query: str, limit: int) -> list[MemoryEntryRow]:
        terms = sorted(set(_TERM.findall(query.lower())))
        if not terms:
            return []
        ts_query = func.to_tsquery(_TS_CONFIG, " | ".join(terms))
        vector = func.to_tsvector(_TS_CONFIG, MemoryEntryRow.content)
        rank = func.ts_rank(vector, ts_query)
        rows = (
            await self._session.scalars(
                select(MemoryEntryRow)
                .where(vector.op("@@")(ts_query))
                .order_by(rank.desc(), MemoryEntryRow.created_at.desc())
                .limit(limit)
            )
        ).all()
        if rows:
            await self._session.execute(
                update(MemoryEntryRow)
                .where(MemoryEntryRow.id.in_([row.id for row in rows]))
                .values(use_count=MemoryEntryRow.use_count + 1)
            )
        return list(rows)

    async def add(
        self, kind: MemoryKind, contents: list[str], source_run_id: uuid.UUID | None
    ) -> list[str]:
        """Insert new entries; duplicates (by normalised content) are ignored."""
        added = []
        for content in contents:
            statement = (
                insert(MemoryEntryRow)
                .values(
                    id=uuid.uuid4(),
                    kind=kind,
                    content=content.strip(),
                    content_hash=content_hash(content),
                    source_run_id=source_run_id,
                )
                .on_conflict_do_nothing(index_elements=["content_hash"])
                .returning(MemoryEntryRow.id)
            )
            if await self._session.scalar(statement) is not None:
                added.append(content.strip())
        return added
