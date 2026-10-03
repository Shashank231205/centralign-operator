"""Runs one action through the tool registry and always returns an Observation.

Recovery at this level is deliberately narrow: transient failures of *read* actions are retried
with backoff. Writes are never blindly retried — the runtime's idempotency check decides
whether a write needs repeating, so a lost acknowledgement cannot create a duplicate.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.core.errors import AgentError
from app.core.resilience import RetryPolicy, with_timeout
from app.domain.enums import FailureKind, RiskLevel
from app.domain.models import Action, Assessment, Observation
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry


@dataclass(frozen=True, slots=True)
class Execution:
    observation: Observation
    attempts: int


class Executor:
    def __init__(
        self,
        registry: ToolRegistry,
        retry: RetryPolicy,
        action_timeout_seconds: float,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self._registry = registry
        self._retry = retry
        self._timeout = action_timeout_seconds
        self._sleep = sleep
        self._rng = rng or random.Random()  # noqa: S311  # jitter, not cryptography

    async def assess(self, action: Action, ctx: ToolContext) -> Assessment:
        tool = self._registry.get(action.tool)
        return await tool.assess(tool.parse(action.args), ctx)

    async def execute(
        self,
        action: Action,
        assessment: Assessment,
        ctx: ToolContext,
        on_retry: Callable[[int, str, float], None],
    ) -> Execution:
        retryable = assessment.risk is RiskLevel.READ
        attempt = 0
        while True:
            attempt += 1
            observation = await self._attempt(action, ctx)
            transient = observation.failure_kind is FailureKind.TRANSIENT
            if not (transient and retryable and attempt < self._retry.max_attempts):
                return Execution(observation, attempt)
            delay = self._retry.backoff(attempt, self._rng)
            on_retry(attempt, observation.error or "transient failure", delay)
            await self._sleep(delay)

    async def _attempt(self, action: Action, ctx: ToolContext) -> Observation:
        tool = self._registry.get(action.tool)
        try:
            args = tool.parse(action.args)
            return await with_timeout(tool.run(args, ctx), self._timeout, action.tool)
        except AgentError as exc:
            return Observation(
                ok=False,
                summary=f"{action.tool} failed: {exc.message}",
                error=exc.message,
                failure_kind=exc.failure_kind,
            )
