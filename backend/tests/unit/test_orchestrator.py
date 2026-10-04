from typing import Any, cast
from uuid import uuid4

import pytest

from app.agent.executor.executor import Executor
from app.agent.observer.observer import Observer
from app.agent.runtime.budget import BudgetGuard
from app.agent.runtime.orchestrator import AgentRuntime
from app.core.config import AgentSettings
from app.core.resilience import RetryPolicy
from app.domain.enums import ApprovalDecision, RunStatus
from app.domain.events import EventType
from app.domain.models import ApprovalResolution, RunState
from app.services.approvals import _apply
from app.tools.control import control_tools
from app.tools.registry import ToolRegistry
from tests.unit.fakes import (
    FakeMemory,
    FakeRead,
    FakeVerifier,
    FakeWrite,
    MemoryRecorder,
    ScriptedStages,
    decision,
    tool_context,
)

SETTINGS = AgentSettings()


async def _noop_sleep(_: float) -> None:
    return None


def runtime(stages: ScriptedStages, verifier: FakeVerifier, memory: FakeMemory) -> AgentRuntime:
    registry = ToolRegistry([FakeRead(), FakeWrite(), *control_tools()])
    return AgentRuntime(
        stages=cast(Any, stages),
        executor=Executor(registry, RetryPolicy(2, 0, 0), 5.0, sleep=_noop_sleep),
        verifier=cast(Any, verifier),
        observer=Observer(SETTINGS),
        budget=BudgetGuard(SETTINGS),
        memory=memory,
        settings=SETTINGS,
    )


@pytest.fixture(autouse=True)
def reset_tool_counters() -> None:
    FakeRead.calls = 0
    FakeWrite.calls = 0


async def test_happy_path_completes_verifies_and_learns() -> None:
    memory, recorder = FakeMemory(), MemoryRecorder()
    stages = ScriptedStages([decision("fake_read"), decision("finish", summary="done")])
    state = RunState(run_id=uuid4(), request="do the thing")
    await runtime(stages, FakeVerifier([True]), memory).advance(state, tool_context(), recorder)
    assert state.status is RunStatus.COMPLETED
    assert state.facts == {"n": "1"}
    assert EventType.VERIFICATION_RESULT in recorder.types()
    assert recorder.types()[-1] is EventType.RUN_COMPLETED
    assert memory.learned == ["ERP needs DD/MM/YYYY"]
    assert FakeRead.calls == 1


async def test_high_value_write_pauses_for_approval_then_resumes_under_grant() -> None:
    recorder = MemoryRecorder()
    stages = ScriptedStages(
        [
            decision("fake_write", amount="7450.00"),
            decision("fake_write", amount="7450.00"),
            decision("finish", summary="done"),
        ]
    )
    agent = runtime(stages, FakeVerifier([True]), FakeMemory())
    state = RunState(run_id=uuid4(), request="enter invoice")
    ctx = tool_context()
    await agent.advance(state, ctx, recorder)
    assert state.status is RunStatus.AWAITING_APPROVAL
    assert FakeWrite.calls == 0
    assert recorder.approvals[0].assessment.payload == {"amount": "7450.00"}

    assert state.pending_approval is not None
    _apply(state, state.pending_approval, ApprovalResolution(decision=ApprovalDecision.APPROVE))
    state.status = RunStatus.EXECUTING
    await agent.advance(state, ctx, recorder)
    assert state.status is RunStatus.COMPLETED
    assert FakeWrite.calls == 1
    assert state.grants == []


async def test_edited_approval_only_covers_the_edited_values() -> None:
    stages = ScriptedStages(
        [decision("fake_write", amount="7450.00"), decision("fake_write", amount="7450.00")]
    )
    agent = runtime(stages, FakeVerifier([True]), FakeMemory())
    state, recorder, ctx = RunState(run_id=uuid4(), request="x"), MemoryRecorder(), tool_context()
    await agent.advance(state, ctx, recorder)
    assert state.pending_approval is not None
    _apply(
        state,
        state.pending_approval,
        ApprovalResolution(
            decision=ApprovalDecision.APPROVE_WITH_EDITS, edited_payload={"amount": "7400.00"}
        ),
    )
    state.status = RunStatus.EXECUTING
    await agent.advance(state, ctx, recorder)
    assert state.status is RunStatus.AWAITING_APPROVAL
    assert FakeWrite.calls == 0


async def test_write_is_skipped_when_outcome_already_exists() -> None:
    recorder = MemoryRecorder()
    stages = ScriptedStages([decision("fake_write", amount="10")])
    state = RunState(run_id=uuid4(), request="enter invoice")
    verifier = FakeVerifier([True], already_satisfied=True)
    await runtime(stages, verifier, FakeMemory()).advance(state, tool_context(), recorder)
    assert state.status is RunStatus.COMPLETED
    assert FakeWrite.calls == 0
    assert EventType.IDEMPOTENT_SKIP in recorder.types()


async def test_failed_verification_gets_one_repair_then_fails() -> None:
    recorder = MemoryRecorder()
    stages = ScriptedStages([decision("finish", summary="a"), decision("finish", summary="b")])
    state = RunState(run_id=uuid4(), request="x")
    verifier = FakeVerifier([False, False])
    await runtime(stages, verifier, FakeMemory()).advance(state, tool_context(), recorder)
    assert state.status is RunStatus.FAILED
    assert verifier.verify_calls == 2
    assert state.plan is not None and state.plan.version == 2
    assert EventType.PLAN_REVISED in recorder.types()


async def test_unknown_tool_becomes_an_observation_not_a_crash() -> None:
    recorder = MemoryRecorder()
    stages = ScriptedStages([decision("no_such_tool"), decision("finish", summary="ok")])
    state = RunState(run_id=uuid4(), request="x")
    await runtime(stages, FakeVerifier([True]), FakeMemory()).advance(
        state, tool_context(), recorder
    )
    assert state.status is RunStatus.COMPLETED
    assert recorder.steps[0].observation.ok is False
    assert "Unknown tool" in (recorder.steps[0].observation.error or "")
