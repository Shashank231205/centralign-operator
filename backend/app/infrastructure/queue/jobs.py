"""arq job queue: the API enqueues, workers execute. Scaling out = running more workers."""

import uuid

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings as ArqRedisSettings

from app.core.config import RedisSettings

EXECUTE_RUN_JOB = "execute_run"


def arq_settings(settings: RedisSettings) -> ArqRedisSettings:
    arq = ArqRedisSettings.from_dsn(settings.url.get_secret_value())
    arq.conn_timeout = int(settings.connect_timeout_seconds)
    return arq


class RunQueue:
    def __init__(self, pool: ArqRedis, queue_name: str) -> None:
        self._pool = pool
        self._queue_name = queue_name

    @classmethod
    async def connect(cls, settings: RedisSettings) -> "RunQueue":
        return cls(await create_pool(arq_settings(settings)), settings.queue_name)

    async def enqueue(self, run_id: uuid.UUID) -> None:
        await self._pool.enqueue_job(EXECUTE_RUN_JOB, str(run_id), _queue_name=self._queue_name)

    async def close(self) -> None:
        await self._pool.aclose()
