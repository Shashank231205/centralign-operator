"""Redis-backed coordination: live event fan-out, per-run locks, cancellation and idempotency."""

import secrets
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis

_RELEASE_IF_OWNER = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


class EventBus:
    """Pub/sub fan-out of run events to SSE subscribers on any API instance."""

    def __init__(self, redis: Redis, channel_prefix: str) -> None:
        self._redis = redis
        self._prefix = channel_prefix

    def _channel(self, run_id: uuid.UUID) -> str:
        return f"{self._prefix}:{run_id}"

    async def publish(self, run_id: uuid.UUID, message: str) -> None:
        await self._redis.publish(self._channel(run_id), message)

    @asynccontextmanager
    async def subscribe(self, run_id: uuid.UUID) -> AsyncIterator[AsyncIterator[str]]:
        """Subscribe *before* yielding, so callers can replay history without missing events."""
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._channel(run_id))

        async def messages() -> AsyncIterator[str]:
            async for item in pubsub.listen():
                if item.get("type") == "message":
                    yield str(item["data"])

        try:
            yield messages()
        finally:
            await pubsub.unsubscribe(self._channel(run_id))
            await pubsub.aclose()  # type: ignore[no-untyped-call]  # redis-py lacks the annotation


class RunLock:
    """At most one worker executes a run at a time (SET NX PX + owner-checked release)."""

    def __init__(self, redis: Redis, run_id: uuid.UUID, ttl_seconds: int) -> None:
        self._redis = redis
        self._key = f"operator:lock:run:{run_id}"
        self._ttl_ms = ttl_seconds * 1000
        self._token = secrets.token_hex(16)
        self._release = redis.register_script(_RELEASE_IF_OWNER)

    async def acquire(self) -> bool:
        return bool(await self._redis.set(self._key, self._token, nx=True, px=self._ttl_ms))

    async def release(self) -> None:
        await self._release(keys=[self._key], args=[self._token])


class CancelFlags:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    async def request(self, run_id: uuid.UUID) -> None:
        await self._redis.set(f"operator:cancel:{run_id}", "1", ex=self._ttl)

    async def is_requested(self, run_id: uuid.UUID) -> bool:
        return bool(await self._redis.exists(f"operator:cancel:{run_id}"))


class IdempotencyCache:
    """Fast path for Idempotency-Key replays; the database unique constraint is the backstop."""

    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    async def get(self, key: str) -> uuid.UUID | None:
        value = await self._redis.get(f"operator:idem:{key}")
        return uuid.UUID(str(value)) if value else None

    async def put(self, key: str, run_id: uuid.UUID) -> None:
        await self._redis.set(f"operator:idem:{key}", str(run_id), ex=self._ttl)
