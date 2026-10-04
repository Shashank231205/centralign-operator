"""The operator's control loop.

    Goal → Understand → Plan → Execute ⇄ Observe → (Re-plan) → Verify → Complete
                                   ↘ ask human / await approval → resume

Each iteration handles exactly one status, checkpoints, and moves on; the loop stops when the
run is finished or paused for a human. Nothing here knows about any specific task: all task
knowledge arrives through company context, the plan and observations.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import uuid4

from app.agent.executor.executor import Executor
from app.agent.observer.observer import Observer, Signal
from app.agent.policy.engine import PolicyEngine, Verdict
from app.agent.runtime.budget import BudgetGuard, RunUsage
from app.agent.runtime.ports import CompanyMemory, RunRecorder
from app.agent.runtime.state_machine import ensure_transition
from app.agent.stages import Stages
from app.agent.understanding.context import Procedure
from app.agent.verifier.verifier import Verifier
from app.core.config import AgentSettings
from app.core.errors import AgentError, BudgetExceededError, LLMResponseInvalidError
from app.domain.enums import EvidenceKind, FailureKind, RiskLevel, RunStatus, StepStatus
from app.domain.events import DomainEvent, EventType
from app.domain.models import (
    Action,
    Assessment,
    NextAction,
    Observation,
    PendingApproval,
    RunState,
    StepRecord,
)
from app.tools.base import ToolContext
from app.tools.control import ASK_HUMAN, FINISH, REPLAN

logger = logging.getLogger(__name__)

LESSON_FACT_PREFIX = "lesson_"


@dataclass(slots=True)
class AgentRuntime:
    stages: Stages
    executor: Executor
    verifier: Verifier
    observer: Observer
    budget: BudgetGuard
    memory: CompanyMemory
    settings: AgentSettings

    async def advance(self, state: RunState, ctx: ToolContext, recorder: RunRecorder) -> RunState:
        """Drive the run until it completes, fails, is cancelled or waits for a human."""
        await RunSession(self, state, ctx, recorder).drive()
        return state


class RunSession:
    def __init__(
        self, runtime: AgentRuntime, state: RunState, ctx: ToolContext, recorder: RunRecorder
    ) -> None:
        self._rt = runtime
        self.state = state
        self._ctx = ctx
        self._recorder = recorder
        self._usage = RunUsage(state)
        self._lessons: list[str] | None = None
        self._handlers: dict[RunStatus, Callable[[], Awaitable[None]]] = {
            RunStatus.PENDING: self._start,
            RunStatus.UNDERSTANDING: self._understand,
            RunStatus.PLANNING: self._plan,
            RunStatus.REPLANNING: self._replan,
            RunStatus.EXECUTING: self._execute_step,
            RunStatus.VERIFYING: self._verify,
        }

    async def drive(self) -> None:
        try:
            while not (self.state.status.is_terminal or self.state.status.is_paused):
                if await self._recorder.cancel_requested(self.state):
                    await self._transition(RunStatus.CANCELLED, "Cancelled on request")
                    break
                self._rt.budget.check(self.state)
                await self._handlers[self.state.status]()
                await self._recorder.checkpoint(self.state)
        except (BudgetExceededError, LLMResponseInvalidError) as exc:
            await self._fail(exc.message)

    # --- stages ------------------------------------------------------------------------

    async def _start(self) -> None:
        await self._transition(RunStatus.UNDERSTANDING, "Interpreting the request")

    async def _understand(self) -> None:
        query = " ".join([self.state.request, *self.state.human_inputs])
        procedures = self._ctx.company.retrieve_procedures(query, self._rt.settings.context_top_k)
        lessons = await self._lessons_for(query)
        await self._emit(
            EventType.CONTEXT_RETRIEVED,
            f"Retrieved {len(procedures)} procedure(s) and {len(lessons)} lesson(s)",
            procedures=[procedure.id for procedure in procedures],
            lessons=lessons,
        )
        goal = await self._rt.stages.understand(
            self.state, self._ctx.company, procedures, lessons, self._usage
        )
        self.state.goal = goal
        await self._emit(EventType.GOAL_UNDERSTOOD, goal.intended_outcome, goal=goal.model_dump())
        if goal.blocking_questions:
            await self._ask(" ".join(goal.blocking_questions))
            return
        await self._transition(RunStatus.PLANNING, "Planning")

    async def _plan(self) -> None:
        await self._make_plan(EventType.PLAN_CREATED)

    async def _replan(self) -> None:
        self.state.counters.replans += 1
        self._rt.budget.check(self.state)
        await self._make_plan(EventType.PLAN_REVISED)

    async def _make_plan(self, event: EventType) -> None:
        lessons = await self._lessons_for(self.state.request)
        plan = await self._rt.stages.plan(
            self.state, self._ctx.company, self._goal_procedures(), lessons, self._usage
        )
        reason = self.state.replan_reason
        self.state.plan = plan
        self.state.replan_reason = None
        self.state.counters.consecutive_failures = 0
        await self._emit(
            event,
            f"Plan v{plan.version}: {len(plan.steps)} steps, "
            f"{len(plan.success_criteria)} success criteria",
            plan=plan.model_dump(),
            reason=reason,
        )
        await self._transition(RunStatus.EXECUTING, "Executing plan")

    async def _execute_step(self) -> None:
        lessons = await self._lessons_for(self.state.request)
        decision = await self._rt.stages.decide(self.state, self._ctx.company, lessons, self._usage)
        await self._absorb(decision)
        action = Action(
            tool=decision.tool,
            args=decision.args,
            rationale=decision.thought,
            step_id=decision.step_id,
        )
        await self._emit(EventType.ACTION_PROPOSED, decision.thought, action=action.model_dump())
        if await self._handle_control(action):
            return
        try:
            assessment = await self._rt.executor.assess(action, self._ctx)
        except AgentError as exc:
            await self._record(action, _failure(exc.message, exc.failure_kind), attempts=0)
            return
        if not await self._permitted(action, assessment):
            return
        if assessment.risk is not RiskLevel.READ and await self._outcome_already_present():
            return
        await self._run(action, assessment)

    async def _verify(self) -> None:
        assert self.state.plan is not None
        results = await self._rt.verifier.verify(
            self.state.plan.success_criteria, self.state.facts, self._ctx
        )
        self.state.verification = results
        for result in results:
            await self._emit(
                EventType.VERIFICATION_RESULT,
                f"{'PASS' if result.passed else 'FAIL'} {result.criterion_id}: {result.detail}",
                result=result.model_dump(),
            )
        await self._save_json(
            "verification.json",
            [r.model_dump() for r in results],
            EvidenceKind.VERIFICATION,
            "Independent verification results",
        )
        if all(result.passed for result in results):
            await self._complete()
        elif not self.state.repair_attempted:
            self.state.repair_attempted = True
            failed = "; ".join(f"{r.criterion_id}: {r.detail}" for r in results if not r.passed)
            self.state.replan_reason = f"Verification failed — repair needed: {failed}"
            await self._transition(RunStatus.REPLANNING, "Verification failed; repairing once")
        else:
            await self._fail("Outcome could not be verified after one repair attempt")

    # --- execution helpers -------------------------------------------------------------

    async def _absorb(self, decision: NextAction) -> None:
        new_facts = {
            key: value
            for key, value in decision.remember.items()
            if self.state.facts.get(key) != value
        }
        self.state.facts.update(new_facts)
        if new_facts:
            await self._emit(EventType.FACT_LEARNED, ", ".join(new_facts), facts=new_facts)
        if self.state.plan:
            for step_id in decision.completed_step_ids:
                if step := self.state.plan.step(step_id):
                    step.status = StepStatus.DONE
            if (
                step := self.state.plan.step(decision.step_id)
            ) and step.status is StepStatus.PENDING:
                step.status = StepStatus.IN_PROGRESS

    async def _handle_control(self, action: Action) -> bool:
        if action.tool == FINISH:
            self.state.summary = str(action.args.get("summary", ""))
            await self._transition(RunStatus.VERIFYING, "Verifying the outcome independently")
            return True
        if action.tool == ASK_HUMAN:
            await self._ask(str(action.args.get("question", "")))
            return True
        if action.tool == REPLAN:
            self.state.replan_reason = str(action.args.get("reason", "requested by executor"))
            await self._transition(RunStatus.REPLANNING, self.state.replan_reason)
            return True
        return False

    async def _permitted(self, action: Action, assessment: Assessment) -> bool:
        decision = PolicyEngine(self._ctx.company.policies).evaluate(assessment)
        if decision.verdict is Verdict.FORBID:
            await self._emit(EventType.POLICY_BLOCKED, decision.reason, rules=decision.rule_ids)
            await self._record(
                action,
                _failure(f"Forbidden by policy: {decision.reason}", FailureKind.POLICY),
                attempts=0,
            )
            return False
        if decision.verdict is Verdict.REQUIRE_APPROVAL:
            grant = next(
                (g for g in self.state.grants if g.covers(assessment.system, assessment.payload)),
                None,
            )
            if grant is None:
                await self._request_approval(action, assessment, decision.rule_ids, decision.reason)
                return False
            self.state.grants.remove(grant)
            await self._emit(
                EventType.APPROVAL_RESOLVED,
                "Proceeding under human approval",
                approval_id=str(grant.approval_id),
            )
        return True

    async def _request_approval(
        self, action: Action, assessment: Assessment, rule_ids: list[str], reason: str
    ) -> None:
        pending = PendingApproval(
            approval_id=uuid4(),
            action=action,
            assessment=assessment,
            rule_ids=rule_ids,
            reason=reason,
            evidence=self.state.history[-1].observation.artifacts if self.state.history else [],
        )
        self.state.pending_approval = pending
        await self._recorder.open_approval(self.state, pending)
        await self._emit(EventType.APPROVAL_REQUESTED, reason, approval=pending.model_dump())
        await self._transition(RunStatus.AWAITING_APPROVAL, "Waiting for approval")

    async def _outcome_already_present(self) -> bool:
        """Idempotency: before any write, check whether the post-conditions already hold."""
        plan = self.state.plan
        if plan is None or not await self._rt.verifier.already_satisfied(
            plan.success_criteria, self.state.facts, self._ctx
        ):
            return False
        await self._emit(
            EventType.IDEMPOTENT_SKIP,
            "Outcome already present in the system of record; write skipped",
        )
        self.state.summary = (self.state.summary or "") + " Outcome already existed; no write made."
        await self._transition(RunStatus.VERIFYING, "Verifying the existing outcome")
        return True

    async def _run(self, action: Action, assessment: Assessment) -> None:
        retries: list[tuple[int, str, float]] = []
        execution = await self._rt.executor.execute(
            action,
            assessment,
            self._ctx,
            on_retry=lambda attempt, error, delay: retries.append((attempt, error, delay)),
        )
        for attempt, error, delay in retries:
            await self._emit(
                EventType.ACTION_RETRIED,
                f"Retry {attempt} after {delay:.1f}s: {error}",
                tool=action.tool,
            )
        record = await self._record(action, execution.observation, execution.attempts)
        verdict = self._rt.observer.after_step(self.state, record)
        if verdict.signal is Signal.REPLAN:
            self.state.replan_reason = verdict.reason
            await self._transition(RunStatus.REPLANNING, verdict.reason)
        elif verdict.signal is Signal.FAIL:
            await self._fail(verdict.reason)

    async def _record(self, action: Action, observation: Observation, attempts: int) -> StepRecord:
        counters = self.state.counters
        counters.steps += 1
        counters.retries += max(0, attempts - 1)
        record = StepRecord(
            index=counters.steps, action=action, observation=observation, attempts=attempts
        )
        self.state.history.append(record)
        del self.state.history[: -self._rt.settings.checkpoint_history_limit]
        self.state.location = observation.location or self.state.location
        await self._recorder.record_step(self.state, record)
        for artifact in observation.artifacts:
            await self._recorder.add_evidence(self.state, artifact)
        await self._emit(
            EventType.ACTION_EXECUTED,
            f"{action.tool}: {'ok' if observation.ok else observation.error}",
            step=record.index,
            tool=action.tool,
            ok=observation.ok,
            error=observation.error,
            artifacts=[artifact.model_dump() for artifact in observation.artifacts],
        )
        return record

    # --- endings -----------------------------------------------------------------------

    async def _complete(self) -> None:
        report = await self._rt.stages.report(self.state, self._ctx.company, self._usage)
        self.state.summary = report.summary
        self.state.key_results = report.key_results
        await self._save_json(
            "result.json",
            {
                "summary": report.summary,
                "key_results": report.key_results,
                "facts": self.state.facts,
            },
            EvidenceKind.EXTRACTED_DATA,
            "Final result and extracted values",
        )
        await self._learn(report.lessons)
        await self._transition(RunStatus.COMPLETED, "Completed and verified")
        await self._emit(EventType.RUN_COMPLETED, report.summary, key_results=report.key_results)

    async def _learn(self, reported: list[str]) -> None:
        lessons = reported + [
            value for key, value in self.state.facts.items() if key.startswith(LESSON_FACT_PREFIX)
        ]
        if not lessons:
            return
        added = await self._rt.memory.learn(lessons, str(self.state.run_id))
        if added:
            await self._emit(
                EventType.MEMORY_WRITTEN, f"Learned {len(added)} lesson(s)", lessons=added
            )

    async def _fail(self, reason: str) -> None:
        self.state.failure_reason = reason
        await self._transition(RunStatus.FAILED, reason)
        await self._emit(EventType.RUN_FAILED, reason)

    async def _ask(self, question: str) -> None:
        self.state.pending_question = question
        await self._emit(EventType.INPUT_REQUESTED, question)
        await self._transition(RunStatus.AWAITING_INPUT, "Waiting for the requester")

    # --- plumbing ----------------------------------------------------------------------

    async def _transition(self, target: RunStatus, message: str) -> None:
        ensure_transition(self.state.status, target)
        previous = self.state.status
        self.state.status = target
        await self._recorder.checkpoint(self.state)
        await self._emit(EventType.STATUS_CHANGED, message, previous=previous, status=target)

    async def _emit(self, event_type: EventType, message: str, **data: object) -> None:
        await self._recorder.emit(
            self.state, DomainEvent(type=event_type, message=message, data=data)
        )

    async def _lessons_for(self, query: str) -> list[str]:
        if self._lessons is None:
            self._lessons = await self._rt.memory.recall(query, self._rt.settings.memory_top_k)
        return self._lessons

    def _goal_procedures(self) -> list[Procedure]:
        wanted = set(self.state.goal.procedure_ids if self.state.goal else [])
        chosen = [p for p in self._ctx.company.procedures if p.id in wanted]
        return chosen or self._ctx.company.retrieve_procedures(
            self.state.request, self._rt.settings.context_top_k
        )

    async def _save_json(
        self, name: str, payload: object, kind: EvidenceKind, description: str
    ) -> None:
        artifact = await self._ctx.evidence.save(
            self.state.run_id,
            name,
            json.dumps(payload, indent=2, default=str).encode(),
            kind,
            description,
        )
        await self._recorder.add_evidence(self.state, artifact)


def _failure(message: str, kind: FailureKind) -> Observation:
    return Observation(ok=False, summary=message, error=message, failure_kind=kind)
