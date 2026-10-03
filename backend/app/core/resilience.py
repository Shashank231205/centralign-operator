"""Retry with exponential backoff + full jitter, per-call timeouts, and a circuit breaker."""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum

from app.core.config import ResilienceSettings
from app.core.errors import CircuitOpenError, ToolTimeoutError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float

    @classmethod
    def from_settings(cls, settings: ResilienceSettings) -> "RetryPolicy":
        return cls(
            max_attempts=settings.retry_max_attempts,
            base_delay_seconds=settings.retry_base_delay_seconds,
            max_delay_seconds=settings.retry_max_delay_seconds,
        )

    def backoff(self, attempt: int, rng: random.Random) -> float:
        """Full jitter (AWS architecture blog): uniform(0, min(cap, base * 2^attempt))."""
        ceiling = min(self.max_delay_seconds, self.base_delay_seconds * (2 ** (attempt - 1)))
        return rng.uniform(0, ceiling)


_jitter_rng = random.Random()  # noqa: S311  # jitter, not cryptography


async def retry_async[T](
    operation: Callable[[], Awaitable[T]],
    policy: RetryPolicy,
    *,
    retry_on: tuple[type[BaseException], ...],
    give_up_on: tuple[type[BaseException], ...] = (),
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> T:
    """Run ``operation``; on a retryable error wait with jittered backoff and try again.

    ``give_up_on`` carves exceptions out of ``retry_on`` (e.g. a 429 where failing over beats
    waiting). A server-provided ``retry_after_seconds`` wins over computed backoff.
    """
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await operation()
        except retry_on as exc:
            if isinstance(exc, give_up_on) or attempt == policy.max_attempts:
                raise
            delay = getattr(exc, "retry_after_seconds", None) or policy.backoff(
                attempt, _jitter_rng
            )
            delay = min(float(delay), policy.max_delay_seconds)
            if on_retry:
                on_retry(attempt, exc, delay)
            await asyncio.sleep(delay)
    raise AssertionError("unreachable: loop always returns or raises")


async def with_timeout[T](operation: Awaitable[T], seconds: float, what: str) -> T:
    try:
        async with asyncio.timeout(seconds):
            return await operation
    except TimeoutError as exc:
        raise ToolTimeoutError(f"{what} timed out after {seconds:.0f}s") from exc


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Stops hammering a dependency that keeps failing; probes again after ``reset_seconds``.

    State is per process, which is the usual trade-off: each worker learns independently and
    no shared store sits on the hot path.
    """

    name: str
    failure_threshold: int
    reset_seconds: float
    clock: Callable[[], float] = time.monotonic
    _failures: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)

    @property
    def state(self) -> BreakerState:
        if self._opened_at is None:
            return BreakerState.CLOSED
        if self.clock() - self._opened_at >= self.reset_seconds:
            return BreakerState.HALF_OPEN
        return BreakerState.OPEN

    def ensure_closed(self) -> None:
        if self.state is BreakerState.OPEN:
            raise CircuitOpenError(
                f"Circuit '{self.name}' is open after repeated failures",
                details={"breaker": self.name},
            )

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        # A failed half-open probe re-opens immediately; otherwise wait for the threshold.
        if self.state is BreakerState.HALF_OPEN or self._failures >= self.failure_threshold:
            logger.warning("circuit opened", extra={"breaker": self.name})
            self._opened_at = self.clock()


class BreakerRegistry:
    """One breaker per dependency key (LLM backend, target host), created on first use."""

    def __init__(self, settings: ResilienceSettings) -> None:
        self._settings = settings
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, name: str) -> CircuitBreaker:
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=self._settings.breaker_failure_threshold,
                reset_seconds=self._settings.breaker_reset_seconds,
            )
        return self._breakers[name]
