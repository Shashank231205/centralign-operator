"""Watches the step stream for patterns a single observation can't reveal: failure streaks
and the agent repeating itself. Either one means the plan no longer fits reality."""

import json
from dataclasses import dataclass
from enum import StrEnum

from app.core.config import AgentSettings
from app.domain.enums import FailureKind
from app.domain.models import RunState, StepRecord


class Signal(StrEnum):
    CONTINUE = "continue"
    REPLAN = "replan"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class ObserverVerdict:
    signal: Signal
    reason: str = ""


class Observer:
    def __init__(self, settings: AgentSettings) -> None:
        self._settings = settings

    def after_step(self, state: RunState, record: StepRecord) -> ObserverVerdict:
        observation = record.observation
        if observation.ok:
            state.counters.consecutive_failures = 0
        else:
            state.counters.consecutive_failures += 1
        if observation.failure_kind is FailureKind.FATAL:
            return ObserverVerdict(Signal.FAIL, f"Unrecoverable error: {observation.error}")
        if state.counters.consecutive_failures >= self._settings.max_consecutive_failures:
            return ObserverVerdict(
                Signal.REPLAN,
                f"{state.counters.consecutive_failures} consecutive failures; "
                f"last error: {observation.error}",
            )
        if self._is_looping(state.history):
            return ObserverVerdict(
                Signal.REPLAN, f"Repeated the same action ({record.action.tool}) without progress"
            )
        return ObserverVerdict(Signal.CONTINUE)

    def _is_looping(self, history: list[StepRecord]) -> bool:
        window = self._settings.max_identical_actions
        if len(history) < window:
            return False
        recent = history[-window:]
        signatures = {
            (record.action.tool, json.dumps(record.action.args, sort_keys=True))
            for record in recent
        }
        outcomes = {record.observation.summary for record in recent}
        return len(signatures) == 1 and len(outcomes) == 1
