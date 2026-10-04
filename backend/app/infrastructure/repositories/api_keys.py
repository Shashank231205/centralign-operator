import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import ApiKeyRow


class ApiKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_active(self, key_hash: str) -> uuid.UUID | None:
        return await self._session.scalar(
            select(ApiKeyRow.id).where(
                ApiKeyRow.key_hash == key_hash, ApiKeyRow.revoked_at.is_(None)
            )
        )

    async def ensure(self, name: str, key_hash: str) -> None:
        await self._session.execute(
            insert(ApiKeyRow)
            .values(id=uuid.uuid4(), name=name, key_hash=key_hash)
            .on_conflict_do_nothing(index_elements=["key_hash"])
        )
