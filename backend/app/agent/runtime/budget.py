"""Per-run limits: steps, replans, LLM tokens and wall-clock time."""

from app.core.config import AgentSettings
from app.core.errors import BudgetExceededError
from app.domain.models import RunState, utcnow
from app.llm.base import Completion


class RunUsage:
    """UsageSink that charges every LLM call to the run's counters."""

    def __init__(self, state: RunState) -> None:
        self._state = state

    def record(self, completion: Completion) -> None:
        counters = self._state.counters
        counters.llm_calls += 1
        counters.prompt_tokens += completion.usage.prompt_tokens
        counters.completion_tokens += completion.usage.completion_tokens


class BudgetGuard:
    def __init__(self, settings: AgentSettings) -> None:
        self._settings = settings

    def check(self, state: RunState) -> None:
        counters = state.counters
        elapsed = (utcnow() - state.started_at).total_seconds()
        limits = {
            "steps": (counters.steps, self._settings.max_steps),
            "replans": (counters.replans, self._settings.max_replans),
            "llm_tokens": (counters.tokens, self._settings.max_llm_tokens),
            "duration_seconds": (int(elapsed), self._settings.max_duration_seconds),
        }
        for name, (used, limit) in limits.items():
            if used > limit:
                raise BudgetExceededError(
                    f"Run budget exceeded: {name} {used} > {limit}",
                    details={"budget": name, "used": used, "limit": limit},
                )
