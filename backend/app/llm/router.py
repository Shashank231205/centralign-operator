"""Failover across LLM backends.

Order comes from configuration. Each backend has its own distributed rate limit, concurrency
cap and circuit breaker; a backend that is rate limited, open-circuited or erroring is skipped
and the next one serves the call. Free tiers hit 429s often, so this is the normal path.
"""

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass

from app.core.config import LLMBackendSettings, LLMSettings, ResilienceSettings
from app.core.errors import (
    CircuitOpenError,
    LLMError,
    LLMRateLimitedError,
    LLMRetryableError,
    LLMUnavailableError,
    RateLimitedError,
)
from app.core.rate_limit import BucketSpec, TokenBucketLimiter
from app.core.resilience import BreakerRegistry, CircuitBreaker, RetryPolicy, retry_async
from app.llm.base import Completion, CompletionRequest, LLMProvider

logger = logging.getLogger(__name__)

# A transient error gets one quick retry on the same backend before failing over.
_SAME_BACKEND_ATTEMPTS = 2


@dataclass(slots=True)
class BackendSlot:
    provider: LLMProvider
    settings: LLMBackendSettings
    breaker: CircuitBreaker
    semaphore: asyncio.Semaphore

    @property
    def bucket(self) -> BucketSpec:
        return BucketSpec.per_minute(self.settings.requests_per_minute, self.settings.burst)


class LLMRouter:
    def __init__(
        self,
        slots: list[BackendSlot],
        limiter: TokenBucketLimiter,
        llm_settings: LLMSettings,
        resilience: ResilienceSettings,
    ) -> None:
        if not slots:
            raise ValueError("No usable LLM backend is configured")
        self._slots = slots
        self._limiter = limiter
        self._rate_wait = llm_settings.rate_limit_wait_seconds
        base = RetryPolicy.from_settings(resilience)
        self._retry = RetryPolicy(
            _SAME_BACKEND_ATTEMPTS, base.base_delay_seconds, base.max_delay_seconds
        )

    @classmethod
    def build(
        cls,
        providers: Mapping[str, LLMProvider],
        llm_settings: LLMSettings,
        resilience: ResilienceSettings,
        limiter: TokenBucketLimiter,
        breakers: BreakerRegistry,
    ) -> "LLMRouter":
        slots = []
        for name in llm_settings.providers:
            backend = llm_settings.backends[name]
            if not backend.is_usable:
                logger.warning("llm backend skipped: no api key", extra={"backend": name})
                continue
            slots.append(
                BackendSlot(
                    provider=providers[name],
                    settings=backend,
                    breaker=breakers.get(f"llm:{name}"),
                    semaphore=asyncio.Semaphore(backend.max_concurrency),
                )
            )
        return cls(slots, limiter, llm_settings, resilience)

    @property
    def fingerprint(self) -> str:
        """Identifies the model chain, so cached answers are never served across model changes."""
        return "|".join(f"{slot.provider.name}:{slot.provider.model}" for slot in self._slots)

    async def complete(self, request: CompletionRequest) -> Completion:
        failures: dict[str, str] = {}
        for slot in self._slots:
            try:
                return await self._call(slot, request)
            except (LLMError, CircuitOpenError, RateLimitedError) as exc:
                failures[slot.provider.name] = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "llm backend failed, failing over",
                    extra={"backend": slot.provider.name, "error": failures[slot.provider.name]},
                )
        raise LLMUnavailableError("All LLM backends failed", details={"backends": failures})

    async def _call(self, slot: BackendSlot, request: CompletionRequest) -> Completion:
        slot.breaker.ensure_closed()
        await self._limiter.wait(f"llm:{slot.provider.name}", slot.bucket, self._rate_wait)
        async with slot.semaphore:
            try:
                completion = await retry_async(
                    lambda: slot.provider.complete(request),
                    self._retry,
                    retry_on=(LLMRetryableError,),
                    give_up_on=(LLMRateLimitedError,),
                )
            except LLMError:
                slot.breaker.record_failure()
                raise
        slot.breaker.record_success()
        return completion
