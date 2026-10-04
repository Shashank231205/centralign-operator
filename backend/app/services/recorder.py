"""Durable RunRecorder: Postgres for checkpoints/audit/evidence, Redis pub/sub for live updates.

Each call is its own short transaction, so a crash loses at most the in-flight step and the run
resumes from the last checkpoint.
"""

import json

from app.domain.events import DomainEvent
from app.domain.models import ArtifactRef, PendingApproval, RunState, StepRecord
from app.infrastructure.cache.coordination import CancelFlags, EventBus
from app.infrastructure.db.engine import Database
from app.infrastructure.db.models import RunEventRow
from app.infrastructure.repositories.approvals import ApprovalRepository
from app.infrastructure.repositories.runs import RunRepository


def event_payload(row: RunEventRow) -> dict[str, object]:
    return {
        "id": row.id,
        "type": row.type,
        "status": row.status,
        "message": row.message,
        "data": row.data,
        "created_at": row.created_at.isoformat(),
    }


class DbRunRecorder:
    def __init__(self, database: Database, bus: EventBus, cancel_flags: CancelFlags) -> None:
        self._database = database
        self._bus = bus
        self._cancel = cancel_flags

    async def checkpoint(self, state: RunState) -> None:
        async with self._database.session() as session:
            await RunRepository(session).save_state(state)

    async def emit(self, state: RunState, event: DomainEvent) -> None:
        async with self._database.session() as session:
            row = await RunRepository(session).append_event(state, event)
            payload = event_payload(row)
        # Publish after commit so subscribers never see an event that might roll back.
        await self._bus.publish(state.run_id, json.dumps(payload, default=str))

    async def record_step(self, state: RunState, record: StepRecord) -> None:
        async with self._database.session() as session:
            await RunRepository(session).add_step(state.run_id, record)

    async def add_evidence(self, state: RunState, artifact: ArtifactRef) -> None:
        async with self._database.session() as session:
            await RunRepository(session).add_evidence(state.run_id, artifact)

    async def open_approval(self, state: RunState, pending: PendingApproval) -> None:
        async with self._database.session() as session:
            await ApprovalRepository(session).open(state.run_id, pending)

    async def cancel_requested(self, state: RunState) -> bool:
        return await self._cancel.is_requested(state.run_id)
