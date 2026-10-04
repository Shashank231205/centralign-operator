"""Test doubles for the runtime: scripted reasoning, in-memory recording, fake tools."""

from typing import Any, ClassVar, cast
from uuid import uuid4

from pydantic import BaseModel

from app.agent.stages import Report
from app.agent.understanding.context import (
    ApprovalRule,
    CompanyContext,
    CompanyProfile,
    Condition,
    Policies,
)
from app.domain.enums import RiskLevel, ToolKind
from app.domain.events import DomainEvent, EventType
from app.domain.models import (
    ArtifactRef,
    Assessment,
    CriterionResult,
    Goal,
    HttpJsonCheck,
    NextAction,
    Observation,
    PendingApproval,
    Plan,
    PlanStep,
    RunState,
    StepRecord,
    SuccessCriterion,
)
from app.tools.base import Tool, ToolContext

COMPANY = CompanyContext(
    company=CompanyProfile(
        name="Test Co", description="", operator_role="clerk", currency_default="USD"
    ),
    systems={},
    policies=Policies(
        approval_rules=[
            ApprovalRule(
                id="high_value",
                description="Over 5000 needs approval",
                systems=["erp"],
                when=Condition(field="amount", op="gt", value=5000),
            )
        ]
    ),
    procedures=[],
)

PLAN = Plan(
    rationale="test",
    steps=[PlanStep(id="s1", intent="do it", tool_hint="fake_write", expected_observation="ok")],
    success_criteria=[
        SuccessCriterion(
            id="c1",
            description="record exists",
            check=HttpJsonCheck(system="erp_api", path="/x", match={"n": "{{facts.n}}"}),
        )
    ],
)


class NoArgs(BaseModel):
    pass


class AmountArgs(BaseModel):
    amount: str


class FakeRead(Tool[NoArgs]):
    name: ClassVar[str] = "fake_read"
    description: ClassVar[str] = "read"
    kind: ClassVar[ToolKind] = ToolKind.HTTP
    args_model = NoArgs
    calls = 0

    async def run(self, args: NoArgs, ctx: ToolContext) -> Observation:
        FakeRead.calls += 1
        return Observation(ok=True, summary="read ok")


class FakeWrite(Tool[AmountArgs]):
    name: ClassVar[str] = "fake_write"
    description: ClassVar[str] = "write"
    kind: ClassVar[ToolKind] = ToolKind.HTTP
    args_model = AmountArgs
    calls = 0

    async def assess(self, args: AmountArgs, ctx: ToolContext) -> Assessment:
        return Assessment(risk=RiskLevel.WRITE, system="erp", payload={"amount": args.amount})

    async def run(self, args: AmountArgs, ctx: ToolContext) -> Observation:
        FakeWrite.calls += 1
        return Observation(
            ok=True,
            summary="saved",
            artifacts=[ArtifactRef(kind="screenshot", path="x.png", description="saved")],
        )


class ScriptedStages:
    """Replays a fixed sequence of decisions, like a recorded model."""

    def __init__(self, decisions: list[NextAction]) -> None:
        self._decisions = list(decisions)

    async def understand(self, *_: Any) -> Goal:
        return Goal(intended_outcome="outcome", procedure_ids=[])

    async def plan(self, state: RunState, *_: Any) -> Plan:
        plan = PLAN.model_copy(deep=True)
        plan.version = (state.plan.version + 1) if state.plan else 1
        return plan

    async def decide(self, *_: Any) -> NextAction:
        return self._decisions.pop(0)

    async def report(self, *_: Any) -> Report:
        return Report(summary="done", key_results={"n": "1"}, lessons=["ERP needs DD/MM/YYYY"])


class FakeVerifier:
    def __init__(self, results: list[bool], already_satisfied: bool = False) -> None:
        self._results = list(results)
        self._already = already_satisfied
        self.verify_calls = 0

    async def verify(self, criteria: list[SuccessCriterion], *_: Any) -> list[CriterionResult]:
        self.verify_calls += 1
        passed = self._results.pop(0)
        return [
            CriterionResult(criterion_id=c.id, description=c.description, passed=passed, detail="")
            for c in criteria
        ]

    async def already_satisfied(self, *_: Any) -> bool:
        return self._already


class MemoryRecorder:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []
        self.steps: list[StepRecord] = []
        self.approvals: list[PendingApproval] = []
        self.evidence: list[ArtifactRef] = []
        self.checkpoints = 0

    async def checkpoint(self, state: RunState) -> None:
        self.checkpoints += 1

    async def emit(self, state: RunState, event: DomainEvent) -> None:
        self.events.append(event)

    async def record_step(self, state: RunState, record: StepRecord) -> None:
        self.steps.append(record)

    async def add_evidence(self, state: RunState, artifact: ArtifactRef) -> None:
        self.evidence.append(artifact)

    async def open_approval(self, state: RunState, pending: PendingApproval) -> None:
        self.approvals.append(pending)

    async def cancel_requested(self, state: RunState) -> bool:
        return False

    def types(self) -> list[EventType]:
        return [event.type for event in self.events]


class FakeMemory:
    def __init__(self) -> None:
        self.learned: list[str] = []

    async def recall(self, query: str, limit: int) -> list[str]:
        return []

    async def learn(self, lessons: list[str], source_run: str) -> list[str]:
        self.learned += lessons
        return lessons


class NullEvidence:
    async def save(self, *_: Any) -> ArtifactRef:
        return ArtifactRef(kind="report", path="r.json", description="r")


def tool_context() -> ToolContext:
    stub = cast(Any, None)
    return ToolContext(
        run_id=uuid4(),
        company=COMPANY,
        workspace=stub,
        evidence=NullEvidence(),
        credentials=stub,
        http=stub,
        browser=stub,
        limiter=stub,
        host_bucket=stub,
        host_rate_wait_seconds=0,
        breakers=stub,
        observation_char_budget=1000,
    )


def decision(tool: str, **args: Any) -> NextAction:
    return NextAction(thought=f"use {tool}", tool=tool, args=args, remember={"n": "1"})
