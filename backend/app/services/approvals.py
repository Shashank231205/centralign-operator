"""Use case: a human resolves an approval request, and the run resumes from its checkpoint.

Approval becomes a single-use grant bound to the exact payload (or the approver's edited
payload); rejection becomes feedback for the agent and for long-term company memory.
"""

import uuid

from app.agent.runtime.state_machine import ensure_transition
from app.core.errors import InvalidStateError, NotFoundError
from app.domain.enums import ApprovalDecision, ApprovalStatus, RunStatus
from app.domain.events import DomainEvent, EventType
from app.domain.models import ApprovalGrant, ApprovalResolution, PendingApproval, RunState
from app.infrastructure.db.engine import Database
from app.infrastructure.queue.jobs import RunQueue
from app.infrastructure.repositories.approvals import ApprovalRepository
from app.infrastructure.repositories.runs import RunRepository
from app.services.memory import PostgresCompanyMemory
from app.services.recorder import DbRunRecorder

_STATUS_FOR = {
    ApprovalDecision.APPROVE: ApprovalStatus.APPROVED,
    ApprovalDecision.REJECT: ApprovalStatus.REJECTED,
    ApprovalDecision.APPROVE_WITH_EDITS: ApprovalStatus.APPROVED_WITH_EDITS,
}


class ApprovalService:
    def __init__(
        self,
        database: Database,
        queue: RunQueue,
        recorder: DbRunRecorder,
        memory: PostgresCompanyMemory,
    ) -> None:
        self._database = database
        self._queue = queue
        self._recorder = recorder
        self._memory = memory

    async def resolve(self, approval_id: uuid.UUID, resolution: ApprovalResolution) -> RunState:
        async with self._database.session() as session:
            approvals, runs = ApprovalRepository(session), RunRepository(session)
            row = await approvals.get(approval_id, for_update=True)
            if row is None:
                raise NotFoundError(f"Approval {approval_id} not found")
            if row.status != ApprovalStatus.PENDING:
                raise InvalidStateError(f"Approval already {row.status}")
            state = await runs.get_state(row.run_id, for_update=True)
            if state is None or state.pending_approval is None:
                raise InvalidStateError("Run is not waiting for this approval")
            ApprovalRepository.resolve(row, _STATUS_FOR[resolution.decision], resolution)
            _apply(state, state.pending_approval, resolution)
            ensure_transition(state.status, RunStatus.EXECUTING)
            state.status = RunStatus.EXECUTING
            await runs.save_state(state)
        await self._recorder.emit(
            state,
            DomainEvent(
                type=EventType.APPROVAL_RESOLVED,
                message=f"{resolution.decision}: {resolution.comment or 'no comment'}",
                data={"approval_id": str(approval_id), **resolution.model_dump(mode="json")},
            ),
        )
        if resolution.decision is ApprovalDecision.REJECT and resolution.comment:
            await self._memory.remember_feedback(
                f"An approver rejected '{row.reason}': {resolution.comment}", str(state.run_id)
            )
        await self._queue.enqueue(state.run_id)
        return state


def _apply(state: RunState, pending: PendingApproval, resolution: ApprovalResolution) -> None:
    description = pending.assessment.description
    state.pending_approval = None
    if resolution.decision is ApprovalDecision.REJECT:
        state.feedback.append(
            f"REJECTED by approver: {description}. Reason: {resolution.comment or 'none given'}. "
            "Do not retry this action; adapt, ask the requester, or finish and explain."
        )
        return
    payload = {key: str(value) for key, value in pending.assessment.payload.items()}
    if resolution.edited_payload:
        payload.update(resolution.edited_payload)
        state.feedback.append(
            f"APPROVED WITH EDITS: {description}. Use these values instead: "
            f"{resolution.edited_payload}. Re-enter them and submit."
        )
    else:
        state.feedback.append(
            f"APPROVED: {description}. If the page was reset, redo the steps with the same "
            "values and submit."
        )
    # Labels are display text that the approver's edits don't touch; bind to the real fields.
    bound = {key: value for key, value in payload.items() if not key.endswith("_label")}
    state.grants.append(
        ApprovalGrant(
            approval_id=pending.approval_id, system=pending.assessment.system, payload=bound
        )
    )
