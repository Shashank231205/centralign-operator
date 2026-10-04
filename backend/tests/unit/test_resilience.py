import random

import pytest

from app.core.errors import CircuitOpenError, LLMRateLimitedError, LLMRetryableError
from app.core.resilience import BreakerState, CircuitBreaker, RetryPolicy, retry_async

FAST = RetryPolicy(max_attempts=3, base_delay_seconds=0.0, max_delay_seconds=0.0)


class Flaky:
    def __init__(self, failures: int, error: Exception) -> None:
        self.calls = 0
        self._failures = failures
        self._error = error

    async def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self._failures:
            raise self._error
        return "ok"


async def test_retries_transient_errors_until_success() -> None:
    operation = Flaky(2, LLMRetryableError("blip"))
    assert await retry_async(operation, FAST, retry_on=(LLMRetryableError,)) == "ok"
    assert operation.calls == 3


async def test_gives_up_after_max_attempts() -> None:
    operation = Flaky(5, LLMRetryableError("down"))
    with pytest.raises(LLMRetryableError):
        await retry_async(operation, FAST, retry_on=(LLMRetryableError,))
    assert operation.calls == FAST.max_attempts


async def test_give_up_on_skips_retry_for_carved_out_errors() -> None:
    operation = Flaky(1, LLMRateLimitedError("429"))
    with pytest.raises(LLMRateLimitedError):
        await retry_async(
            operation, FAST, retry_on=(LLMRetryableError,), give_up_on=(LLMRateLimitedError,)
        )
    assert operation.calls == 1


def test_backoff_is_full_jitter_and_capped() -> None:
    policy = RetryPolicy(max_attempts=5, base_delay_seconds=1.0, max_delay_seconds=4.0)
    rng = random.Random(7)
    delays = [policy.backoff(attempt, rng) for attempt in range(1, 6)]
    assert all(0 <= delay <= 4.0 for delay in delays)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_circuit_opens_then_half_opens_then_closes() -> None:
    clock = Clock()
    breaker = CircuitBreaker("llm:test", failure_threshold=2, reset_seconds=10, clock=clock)
    breaker.record_failure()
    breaker.ensure_closed()
    breaker.record_failure()
    assert breaker.state is BreakerState.OPEN
    with pytest.raises(CircuitOpenError):
        breaker.ensure_closed()
    clock.now = 10
    assert breaker.state is BreakerState.HALF_OPEN
    breaker.record_success()
    assert breaker.state is BreakerState.CLOSED


def test_failed_probe_reopens_immediately() -> None:
    clock = Clock()
    breaker = CircuitBreaker("host:x", failure_threshold=1, reset_seconds=5, clock=clock)
    breaker.record_failure()
    clock.now = 5
    breaker.record_failure()
    assert breaker.state is BreakerState.OPEN
