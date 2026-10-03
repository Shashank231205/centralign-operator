"""Cache-aside store for deterministic LLM calls.

Only calls explicitly marked cacheable (temperature 0, inputs fully captured in the key) are
stored. The key covers the model chain, prompt version and every message, so a change to any
of them is a miss.
"""

import hashlib
import json

from redis.asyncio import Redis

from app.llm.base import CompletionRequest

KEY_PREFIX = "llm:cache:"


class LLMResponseCache:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    @staticmethod
    def key(model_fingerprint: str, prompt_version: str, request: CompletionRequest) -> str:
        material = json.dumps(
            {
                "models": model_fingerprint,
                "prompt": prompt_version,
                "request": request.model_dump(),
            },
            sort_keys=True,
        )
        return KEY_PREFIX + hashlib.sha256(material.encode()).hexdigest()

    async def get(self, key: str) -> str | None:
        value = await self._redis.get(key)
        return str(value) if value is not None else None

    async def put(self, key: str, text: str) -> None:
        await self._redis.set(key, text, ex=self._ttl)
