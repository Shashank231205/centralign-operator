"""Use cases on an existing run: read it, stream its timeline, answer it, cancel it."""

import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

from app.agent.runtime.state_machine import ensure_transition
from app.core.errors import InvalidStateError, NotFoundError
from app.domain.enums import RunStatus
from app.domain.events import DomainEvent, EventType
from app.domain.models import RunState
from app.infrastructure.cache.coordination import CancelFlags, EventBus
from app.infrastructure.db.engine import Database
from app.infrastructure.db.models import EvidenceRow, RunRow, StepRow
from app.infrastructure.queue.jobs import RunQueue
from app.infrastructure.repositories.runs import RunRepository
from app.infrastructure.storage.local import LocalEvidenceStore
from app.services.recorder import DbRunRecorder, event_payload


class RunService:
    def __init__(
        self,
        database: Database,
        queue: RunQueue,
        bus: EventBus,
        cancel_flags: CancelFlags,
        recorder: DbRunRecorder,
        evidence: LocalEvidenceStore,
    ) -> None:
        self._database = database
        self._queue = queue
        self._bus = bus
        self._cancel = cancel_flags
        self._recorder = recorder
        self._evidence = evidence

    async def get(self, run_id: uuid.UUID) -> RunState:
        async with self._database.session() as session:
            state = await RunRepository(session).get_state(run_id)
        if state is None:
            raise NotFoundError(f"Run {run_id} not found")
        return state

    async def page(self, limit: int, before: tuple[datetime, uuid.UUID] | None) -> list[RunRow]:
        async with self._database.session() as session:
            return await RunRepository(session).list_page(limit, before)

    async def steps(self, run_id: uuid.UUID) -> list[StepRow]:
        await self.get(run_id)
        async with self._database.session() as session:
            return await RunRepository(session).steps(run_id)

    async def evidence(self, run_id: uuid.UUID) -> list[EvidenceRow]:
        await self.get(run_id)
        async with self._database.session() as session:
            return await RunRepository(session).evidence(run_id)

    async def evidence_file(self, run_id: uuid.UUID, evidence_id: uuid.UUID) -> Path:
        for row in await self.evidence(run_id):
            if row.id == evidence_id:
                try:
                    return self._evidence.open(row.path)
                except FileNotFoundError as exc:
                    raise NotFoundError("Evidence file is no longer available") from exc
        raise NotFoundError(f"Evidence {evidence_id} not found for run {run_id}")

    async def stream(self, run_id: uuid.UUID, after_id: int) -> AsyncIterator[dict[str, object]]:
        """Replay the audit log after ``after_id``, then follow live events without gaps."""
        await self.get(run_id)
        async with self._bus.subscribe(run_id) as live:
            last_id = after_id
            async with self._database.session() as session:
                history = await RunRepository(session).events_after(run_id, after_id)
            for row in history:
                last_id = row.id
                yield event_payload(row)
            async for raw in live:
                message = json.loads(raw)
                if int(message["id"]) > last_id:
                    last_id = int(message["id"])
                    yield message

    async def answer(self, run_id: uuid.UUID, answer: str) -> RunState:
        async with self._database.session() as session:
            repository = RunRepository(session)
            state = await repository.get_state(run_id, for_update=True)
            if state is None:
                raise NotFoundError(f"Run {run_id} not found")
            if state.status is not RunStatus.AWAITING_INPUT or not state.pending_question:
                raise InvalidStateError("This run is not waiting for an answer")
            state.human_inputs.append(f"Q: {state.pending_question}\nA: {answer}")
            state.pending_question = None
            target = RunStatus.UNDERSTANDING if state.plan is None else RunStatus.EXECUTING
            ensure_transition(state.status, target)
            state.status = target
            await repository.save_state(state)
        await self._recorder.emit(state, DomainEvent(type=EventType.INPUT_RECEIVED, message=answer))
        await self._queue.enqueue(run_id)
        return state

    async def cancel(self, run_id: uuid.UUID) -> RunState:
        state = await self.get(run_id)
        if state.status.is_terminal:
            raise InvalidStateError(f"Run is already {state.status}")
        await self._cancel.request(run_id)
        if state.status.is_paused or state.status is RunStatus.PENDING:
            # No worker holds a paused run, so cancel it here.
            async with self._database.session() as session:
                repository = RunRepository(session)
                locked = await repository.get_state(run_id, for_update=True)
                assert locked is not None
                locked.status = RunStatus.CANCELLED
                await repository.save_state(locked)
                state = locked
            await self._recorder.emit(
                state, DomainEvent(type=EventType.STATUS_CHANGED, message="Cancelled on request")
            )
        return state
