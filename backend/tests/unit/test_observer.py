from uuid import uuid4

from app.agent.observer.observer import Observer, Signal
from app.core.config import AgentSettings
from app.domain.enums import FailureKind
from app.domain.models import Action, Observation, RunState, StepRecord

SETTINGS = AgentSettings(max_consecutive_failures=3, max_identical_actions=3)


def record(
    index: int,
    ok: bool,
    tool: str = "browser_click",
    summary: str = "same",
    failure: FailureKind | None = None,
) -> StepRecord:
    return StepRecord(
        index=index,
        action=Action(tool=tool, args={"ref": "e1"}),
        observation=Observation(
            ok=ok, summary=summary, error=None if ok else "boom", failure_kind=failure
        ),
    )


def feed(records: list[StepRecord]) -> tuple[RunState, Signal]:
    state = RunState(run_id=uuid4(), request="x")
    observer, signal = Observer(SETTINGS), Signal.CONTINUE
    for item in records:
        state.history.append(item)
        signal = observer.after_step(state, item).signal
    return state, signal


def test_failure_streak_triggers_replan() -> None:
    _, signal = feed([record(i, ok=False, summary=f"s{i}") for i in range(3)])
    assert signal is Signal.REPLAN


def test_success_resets_the_streak() -> None:
    state, signal = feed([record(0, False, summary="a"), record(1, True, summary="b")])
    assert signal is Signal.CONTINUE
    assert state.counters.consecutive_failures == 0


def test_identical_action_with_identical_outcome_is_a_loop() -> None:
    _, signal = feed([record(i, ok=True) for i in range(3)])
    assert signal is Signal.REPLAN


def test_fatal_failure_stops_the_run() -> None:
    _, signal = feed([record(0, ok=False, failure=FailureKind.FATAL)])
    assert signal is Signal.FAIL
