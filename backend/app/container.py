"""Composition root: builds concrete infrastructure once and wires it into services."""

from dataclasses import dataclass

from redis.asyncio import Redis

from app.core.config import Settings
from app.infrastructure.cache.redis import create_redis
from app.infrastructure.db.engine import Database


@dataclass(slots=True)
class Container:
    settings: Settings
    database: Database
    redis: Redis

    @classmethod
    def build(cls, settings: Settings) -> "Container":
        return cls(
            settings=settings,
            database=Database(settings.database),
            redis=create_redis(settings.redis),
        )

    async def start(self) -> None:
        """Fail fast if a hard dependency is unreachable at boot."""
        await self.database.ping()
        await self.redis.ping()

    async def close(self) -> None:
        await self.redis.aclose()
        await self.database.dispose()
