"""Public API contract. Built from domain objects and rows; ORM models never leave the server."""

import base64
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.enums import ApprovalDecision, RunStatus
from app.domain.models import (
    CriterionResult,
    Goal,
    PendingApproval,
    Plan,
    RunCounters,
    RunState,
)
from app.infrastructure.db.models import EvidenceRow, RunRow, StepRow


class CreateTaskRequest(BaseModel):
    request: str = Field(min_length=3, max_length=2000, description="What you need done")


class TaskAccepted(BaseModel):
    run_id: uuid.UUID
    status_url: str
    events_url: str
    replayed: bool


class RunListItem(BaseModel):
    id: uuid.UUID
    status: RunStatus
    request: str
    summary: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: RunRow) -> "RunListItem":
        return cls(
            id=row.id,
            status=RunStatus(row.status),
            request=str(row.state.get("request", "")),
            summary=row.summary,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class RunDetail(BaseModel):
    id: uuid.UUID
    status: RunStatus
    request: str
    goal: Goal | None
    plan: Plan | None
    facts: dict[str, str]
    key_results: dict[str, str]
    verification: list[CriterionResult]
    summary: str | None
    failure_reason: str | None
    pending_question: str | None
    pending_approval: PendingApproval | None
    counters: RunCounters
    location: str | None
    started_at: datetime

    @classmethod
    def from_state(cls, state: RunState) -> "RunDetail":
        return cls(
            id=state.run_id,
            status=state.status,
            request=state.request,
            goal=state.goal,
            plan=state.plan,
            facts=state.facts,
            key_results=state.key_results,
            verification=state.verification,
            summary=state.summary,
            failure_reason=state.failure_reason,
            pending_question=state.pending_question,
            pending_approval=state.pending_approval,
            counters=state.counters,
            location=state.location,
            started_at=state.started_at,
        )


class StepView(BaseModel):
    index: int
    tool: str
    ok: bool
    attempts: int
    action: dict[str, Any]
    observation: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, row: StepRow) -> "StepView":
        return cls(
            index=row.index,
            tool=row.tool,
            ok=row.ok,
            attempts=row.attempts,
            action=row.action,
            observation=row.observation,
            created_at=row.created_at,
        )


class EvidenceView(BaseModel):
    id: uuid.UUID
    kind: str
    description: str
    created_at: datetime
    url: str

    @classmethod
    def from_row(cls, row: EvidenceRow, base_path: str) -> "EvidenceView":
        return cls(
            id=row.id,
            kind=row.kind,
            description=row.description,
            created_at=row.created_at,
            url=f"{base_path}/{row.id}",
        )


class AnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=2000)


class ApprovalDecisionRequest(BaseModel):
    decision: ApprovalDecision
    comment: str = Field(default="", max_length=2000)
    edited_payload: dict[str, str] | None = Field(
        default=None, description="Only with approve_with_edits: field → corrected value"
    )


def encode_cursor(created_at: datetime, run_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{created_at.isoformat()}|{run_id}".encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    created_at, run_id = raw.split("|", 1)
    return datetime.fromisoformat(created_at), uuid.UUID(run_id)
