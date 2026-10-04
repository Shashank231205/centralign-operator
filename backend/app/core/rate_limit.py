"""Distributed token-bucket rate limiter on Redis.

The refill-and-take step runs as one Lua script, so concurrent API instances and workers can't
race each other. Redis server time is used so client clock skew doesn't matter.
"""

import asyncio
from dataclasses import dataclass

from redis.asyncio import Redis

from app.core.errors import RateLimitedError

_BUCKET_SCRIPT = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local state = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(state[1]) or capacity
local ts = tonumber(state[2]) or now
tokens = math.min(capacity, tokens + ((now - ts) / 1000.0) * rate)
local allowed = 0
local retry_after = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
else
  retry_after = (cost - tokens) / rate
end
redis.call('HSET', key, 'tokens', tokens, 'ts', now)
redis.call('PEXPIRE', key, math.ceil((capacity / rate) * 1000) + 1000)
return {allowed, tostring(retry_after)}
"""

KEY_PREFIX = "ratelimit:"


@dataclass(frozen=True, slots=True)
class RateDecision:
    allowed: bool
    retry_after_seconds: float


@dataclass(frozen=True, slots=True)
class BucketSpec:
    rate_per_second: float
    capacity: float

    @classmethod
    def per_minute(cls, requests_per_minute: float, burst: float) -> "BucketSpec":
        return cls(rate_per_second=requests_per_minute / 60.0, capacity=max(1.0, burst))


class TokenBucketLimiter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._script = redis.register_script(_BUCKET_SCRIPT)

    async def acquire(self, key: str, spec: BucketSpec, cost: float = 1.0) -> RateDecision:
        allowed, retry_after = await self._script(
            keys=[KEY_PREFIX + key], args=[spec.rate_per_second, spec.capacity, cost]
        )
        return RateDecision(allowed=bool(int(allowed)), retry_after_seconds=float(retry_after))

    async def wait(
        self, key: str, spec: BucketSpec, max_wait_seconds: float, cost: float = 1.0
    ) -> None:
        """Block until a token is available, or raise if that would take longer than allowed."""
        waited = 0.0
        while True:
            decision = await self.acquire(key, spec, cost)
            if decision.allowed:
                return
            if waited + decision.retry_after_seconds > max_wait_seconds:
                raise RateLimitedError(
                    f"Rate limit for '{key}' exceeded",
                    retry_after_seconds=decision.retry_after_seconds,
                )
            await asyncio.sleep(decision.retry_after_seconds)
            waited += decision.retry_after_seconds
