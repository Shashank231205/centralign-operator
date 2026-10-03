"""Domain events. Appended to the run's audit log and streamed live; the timeline and the
final report are projections of this log."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventType(StrEnum):
    STATUS_CHANGED = "status_changed"
    CONTEXT_RETRIEVED = "context_retrieved"
    GOAL_UNDERSTOOD = "goal_understood"
    PLAN_CREATED = "plan_created"
    PLAN_REVISED = "plan_revised"
    ACTION_PROPOSED = "action_proposed"
    ACTION_EXECUTED = "action_executed"
    ACTION_RETRIED = "action_retried"
    FACT_LEARNED = "fact_learned"
    POLICY_BLOCKED = "policy_blocked"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RESOLVED = "approval_resolved"
    INPUT_REQUESTED = "input_requested"
    INPUT_RECEIVED = "input_received"
    IDEMPOTENT_SKIP = "idempotent_skip"
    VERIFICATION_RESULT = "verification_result"
    MEMORY_WRITTEN = "memory_written"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


class DomainEvent(BaseModel):
    type: EventType
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
