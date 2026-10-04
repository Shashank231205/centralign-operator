"""Run aggregate persistence: task, run checkpoint, steps, audit events and evidence index."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.events import DomainEvent
from app.domain.models import ArtifactRef, RunState, StepRecord
from app.infrastructure.db.models import EvidenceRow, RunEventRow, RunRow, StepRow, TaskRow


class RunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, request: str, idempotency_key: str | None, api_key_id: uuid.UUID | None
    ) -> RunState:
        task = TaskRow(request=request, idempotency_key=idempotency_key, api_key_id=api_key_id)
        self._session.add(task)
        await self._session.flush()
        state = RunState(run_id=uuid.uuid4(), request=request)
        self._session.add(
            RunRow(
                id=state.run_id,
                task_id=task.id,
                status=state.status,
                state=state.model_dump(mode="json"),
            )
        )
        await self._session.flush()
        return state

    async def find_by_idempotency_key(self, key: str) -> uuid.UUID | None:
        return await self._session.scalar(
            select(RunRow.id)
            .join(TaskRow, TaskRow.id == RunRow.task_id)
            .where(TaskRow.idempotency_key == key)
        )

    async def get_state(self, run_id: uuid.UUID, *, for_update: bool = False) -> RunState | None:
        query = select(RunRow.state).where(RunRow.id == run_id)
        if for_update:
            query = query.with_for_update()
        raw = await self._session.scalar(query)
        return RunState.model_validate(raw) if raw is not None else None

    async def save_state(self, state: RunState) -> None:
        finished = datetime.now(UTC) if state.status.is_terminal else None
        await self._session.execute(
            update(RunRow)
            .where(RunRow.id == state.run_id)
            .values(
                status=state.status,
                state=state.model_dump(mode="json"),
                summary=state.summary,
                failure_reason=state.failure_reason,
                finished_at=finished,
            )
        )

    async def list_page(
        self, limit: int, before: tuple[datetime, uuid.UUID] | None
    ) -> list[RunRow]:
        query = select(RunRow).order_by(RunRow.created_at.desc(), RunRow.id.desc()).limit(limit)
        if before:
            created_at, run_id = before
            query = query.where(
                (RunRow.created_at < created_at)
                | ((RunRow.created_at == created_at) & (RunRow.id < run_id))
            )
        return list((await self._session.scalars(query)).all())

    async def add_step(self, run_id: uuid.UUID, record: StepRecord) -> None:
        self._session.add(
            StepRow(
                run_id=run_id,
                index=record.index,
                tool=record.action.tool,
                ok=record.observation.ok,
                attempts=record.attempts,
                action=record.action.model_dump(mode="json"),
                observation=record.observation.model_dump(mode="json"),
            )
        )

    async def steps(self, run_id: uuid.UUID) -> list[StepRow]:
        query = select(StepRow).where(StepRow.run_id == run_id).order_by(StepRow.index)
        return list((await self._session.scalars(query)).all())

    async def append_event(self, state: RunState, event: DomainEvent) -> RunEventRow:
        row = RunEventRow(
            run_id=state.run_id,
            type=event.type,
            status=state.status,
            message=event.message,
            data=event.model_dump(mode="json")["data"],
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def events_after(self, run_id: uuid.UUID, after_id: int) -> list[RunEventRow]:
        query = (
            select(RunEventRow)
            .where(RunEventRow.run_id == run_id, RunEventRow.id > after_id)
            .order_by(RunEventRow.id)
        )
        return list((await self._session.scalars(query)).all())

    async def add_evidence(self, run_id: uuid.UUID, artifact: ArtifactRef) -> None:
        self._session.add(
            EvidenceRow(
                run_id=run_id,
                kind=artifact.kind,
                path=artifact.path,
                description=artifact.description,
            )
        )

    async def evidence(self, run_id: uuid.UUID) -> list[EvidenceRow]:
        query = (
            select(EvidenceRow).where(EvidenceRow.run_id == run_id).order_by(EvidenceRow.created_at)
        )
        return list((await self._session.scalars(query)).all())
