"""Core business objects of a run. Pure data: no I/O, no framework or driver imports."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import (
    ApprovalDecision,
    EvidenceKind,
    FailureKind,
    RiskLevel,
    RunStatus,
    StepStatus,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


# --- Understanding -----------------------------------------------------------------------


class OpenQuestion(BaseModel):
    question: str
    blocking: bool = Field(description="True if work cannot safely start without an answer")


class Goal(BaseModel):
    """Structured interpretation of the request: what 'done' means for the requester."""

    intended_outcome: str
    entities: dict[str, str] = Field(
        default_factory=dict, description="Named things the task is about, e.g. vendor name"
    )
    target_systems: list[str] = Field(default_factory=list)
    procedure_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)

    @property
    def blocking_questions(self) -> list[str]:
        return [question.question for question in self.open_questions if question.blocking]


# --- Planning ----------------------------------------------------------------------------


class PlanStep(BaseModel):
    id: str
    intent: str
    tool_hint: str = Field(description="Tool expected to be used, from the tool list")
    expected_observation: str
    risk: RiskLevel = RiskLevel.READ
    status: StepStatus = StepStatus.PENDING


class HttpJsonCheck(BaseModel):
    """Query a read API and count items whose fields match. Values may use {{facts.name}}."""

    kind: Literal["http_json"] = "http_json"
    system: str
    path: str
    params: dict[str, str] = Field(default_factory=dict)
    match: dict[str, str] = Field(default_factory=dict)
    expected_count: int | None = Field(
        default=1, description="Exact number of matching items; null means at least one"
    )


class SourceRef(BaseModel):
    system: str
    path: str
    params: dict[str, str] = Field(default_factory=dict)
    key_field: str


class FileCheck(BaseModel):
    """A workspace file exists, has the columns, and (optionally) the same keys as a source."""

    kind: Literal["file"] = "file"
    path: str
    required_columns: list[str] = Field(default_factory=list)
    key_column: str | None = None
    compare_to: SourceRef | None = None


Check = Annotated[HttpJsonCheck | FileCheck, Field(discriminator="kind")]


class SuccessCriterion(BaseModel):
    id: str
    description: str
    check: Check


class Plan(BaseModel):
    rationale: str
    steps: list[PlanStep]
    success_criteria: list[SuccessCriterion]
    version: int = 1

    def step(self, step_id: str | None) -> PlanStep | None:
        return next((step for step in self.steps if step.id == step_id), None)


# --- Acting ------------------------------------------------------------------------------


class Action(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    step_id: str | None = None


class ArtifactRef(BaseModel):
    kind: EvidenceKind
    path: str
    description: str


class Observation(BaseModel):
    """What happened after an action, normalised for every tool kind."""

    ok: bool
    summary: str = Field(description="Compact text the model reads to decide what to do next")
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    failure_kind: FailureKind | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    location: str | None = None


class Assessment(BaseModel):
    """Pre-execution view of an action, used by policy before anything is sent."""

    risk: RiskLevel
    system: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    description: str = ""


class StepRecord(BaseModel):
    index: int
    action: Action
    observation: Observation
    attempts: int = 1
    at: datetime = Field(default_factory=utcnow)


class NextAction(BaseModel):
    """The model's decision for the next move, made from the latest observation."""

    thought: str = Field(description="One or two sentences: what you observed and why this action")
    step_id: str | None = Field(default=None, description="Plan step this action advances")
    completed_step_ids: list[str] = Field(
        default_factory=list, description="Plan steps the latest observation shows are done"
    )
    remember: dict[str, str] = Field(
        default_factory=dict, description="New facts from the latest observation (name -> value)"
    )
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


# --- Human in the loop -------------------------------------------------------------------


class PendingApproval(BaseModel):
    approval_id: UUID
    action: Action
    assessment: Assessment
    rule_ids: list[str]
    reason: str
    evidence: list[ArtifactRef] = Field(
        default_factory=list, description="What the operator saw just before asking"
    )


class ApprovalResolution(BaseModel):
    decision: ApprovalDecision
    comment: str = ""
    edited_payload: dict[str, str] | None = Field(
        default=None, description="Field values the approver changed, e.g. {'amount': '7400.00'}"
    )


class ApprovalGrant(BaseModel):
    """A human authorised writing this payload to this system. Single use.

    Approvals bind to data, not to a browser element: after a pause (possibly on another
    worker, with a fresh browser) the agent redoes the steps and the matching write passes.
    """

    approval_id: UUID
    system: str | None
    payload: dict[str, str]

    def covers(self, system: str | None, payload: dict[str, Any]) -> bool:
        if system != self.system:
            return False
        return all(
            str(payload.get(key, "")).strip().lower() == value.strip().lower()
            for key, value in self.payload.items()
        )


# --- Verification ------------------------------------------------------------------------


class CriterionResult(BaseModel):
    criterion_id: str
    description: str
    passed: bool
    detail: str
    observed: dict[str, Any] = Field(default_factory=dict)


# --- Run state (the checkpoint) ----------------------------------------------------------


class RunCounters(BaseModel):
    steps: int = 0
    replans: int = 0
    consecutive_failures: int = 0
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    retries: int = 0

    @property
    def tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class RunState(BaseModel):
    """Everything needed to resume a run on any worker after a crash or a long human pause."""

    run_id: UUID
    request: str
    status: RunStatus = RunStatus.PENDING
    goal: Goal | None = None
    plan: Plan | None = None
    facts: dict[str, str] = Field(default_factory=dict)
    history: list[StepRecord] = Field(default_factory=list)
    counters: RunCounters = Field(default_factory=RunCounters)
    pending_approval: PendingApproval | None = None
    grants: list[ApprovalGrant] = Field(default_factory=list)
    pending_question: str | None = None
    human_inputs: list[str] = Field(default_factory=list)
    feedback: list[str] = Field(default_factory=list)
    verification: list[CriterionResult] = Field(default_factory=list)
    repair_attempted: bool = False
    replan_reason: str | None = None
    location: str | None = None
    summary: str | None = None
    key_results: dict[str, str] = Field(default_factory=dict)
    failure_reason: str | None = None
    started_at: datetime = Field(default_factory=utcnow)
