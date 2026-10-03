"""Explicit run lifecycle. Every status change goes through ``transition`` so illegal jumps
fail loudly instead of corrupting a run."""

from app.core.errors import InvalidStateError
from app.domain.enums import RunStatus

_CANCEL_OR_FAIL = {RunStatus.FAILED, RunStatus.CANCELLED}

ALLOWED_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.PENDING: {RunStatus.UNDERSTANDING} | _CANCEL_OR_FAIL,
    RunStatus.UNDERSTANDING: {RunStatus.PLANNING, RunStatus.AWAITING_INPUT} | _CANCEL_OR_FAIL,
    RunStatus.PLANNING: {RunStatus.EXECUTING} | _CANCEL_OR_FAIL,
    RunStatus.EXECUTING: {
        RunStatus.VERIFYING,
        RunStatus.REPLANNING,
        RunStatus.AWAITING_INPUT,
        RunStatus.AWAITING_APPROVAL,
    }
    | _CANCEL_OR_FAIL,
    RunStatus.REPLANNING: {RunStatus.EXECUTING} | _CANCEL_OR_FAIL,
    RunStatus.AWAITING_INPUT: {RunStatus.UNDERSTANDING, RunStatus.EXECUTING} | _CANCEL_OR_FAIL,
    RunStatus.AWAITING_APPROVAL: {RunStatus.EXECUTING} | _CANCEL_OR_FAIL,
    RunStatus.VERIFYING: {RunStatus.COMPLETED, RunStatus.REPLANNING} | _CANCEL_OR_FAIL,
    RunStatus.COMPLETED: set(),
    RunStatus.FAILED: set(),
    RunStatus.CANCELLED: set(),
}


def ensure_transition(current: RunStatus, target: RunStatus) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidStateError(
            f"Run cannot move from {current} to {target}",
            details={"from": current, "to": target},
        )
