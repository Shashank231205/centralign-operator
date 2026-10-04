from itertools import pairwise

import pytest

from app.agent.runtime.state_machine import ALLOWED_TRANSITIONS, ensure_transition
from app.core.errors import InvalidStateError
from app.domain.enums import RunStatus


def test_happy_path_is_allowed() -> None:
    path = [
        RunStatus.PENDING,
        RunStatus.UNDERSTANDING,
        RunStatus.PLANNING,
        RunStatus.EXECUTING,
        RunStatus.VERIFYING,
        RunStatus.COMPLETED,
    ]
    for current, target in pairwise(path):
        ensure_transition(current, target)


def test_pauses_resume_into_execution() -> None:
    ensure_transition(RunStatus.EXECUTING, RunStatus.AWAITING_APPROVAL)
    ensure_transition(RunStatus.AWAITING_APPROVAL, RunStatus.EXECUTING)
    ensure_transition(RunStatus.AWAITING_INPUT, RunStatus.UNDERSTANDING)


def test_cannot_skip_verification() -> None:
    with pytest.raises(InvalidStateError):
        ensure_transition(RunStatus.EXECUTING, RunStatus.COMPLETED)


@pytest.mark.parametrize("terminal", [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED])
def test_terminal_states_are_final(terminal: RunStatus) -> None:
    assert ALLOWED_TRANSITIONS[terminal] == set()
    assert terminal.is_terminal


def test_every_status_has_a_transition_entry() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(RunStatus)
