import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from app.api.deps import ApiKeyDep, ContainerDep
from app.api.v1.schemas.common import Page
from app.api.v1.schemas.runs import (
    AnswerRequest,
    EvidenceView,
    RunDetail,
    RunListItem,
    StepView,
    decode_cursor,
    encode_cursor,
)
from app.core.config import API_PREFIX
from app.core.errors import AppError

router = APIRouter(prefix="/runs", tags=["runs"])


class InvalidCursorError(AppError):
    status_code = 400
    code = "invalid_cursor"


@router.get("", response_model=Page[RunListItem])
async def list_runs(
    container: ContainerDep,
    _: ApiKeyDep,
    limit: Annotated[int | None, Query(ge=1)] = None,
    cursor: str | None = None,
) -> Page[RunListItem]:
    api = container.settings.api
    size = min(limit or api.page_size_default, api.page_size_max)
    try:
        before = decode_cursor(cursor) if cursor else None
    except ValueError as exc:
        raise InvalidCursorError("Malformed cursor") from exc
    rows = await container.runs.page(size + 1, before)
    items = [RunListItem.from_row(row) for row in rows[:size]]
    next_cursor = (
        encode_cursor(rows[size - 1].created_at, rows[size - 1].id) if len(rows) > size else None
    )
    return Page(items=items, next_cursor=next_cursor)


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(run_id: uuid.UUID, container: ContainerDep, _: ApiKeyDep) -> RunDetail:
    return RunDetail.from_state(await container.runs.get(run_id))


@router.get("/{run_id}/steps", response_model=list[StepView])
async def get_steps(run_id: uuid.UUID, container: ContainerDep, _: ApiKeyDep) -> list[StepView]:
    return [StepView.from_row(row) for row in await container.runs.steps(run_id)]


@router.get("/{run_id}/events")
async def stream_events(
    run_id: uuid.UUID,
    container: ContainerDep,
    _: ApiKeyDep,
    last_event_id: Annotated[str | None, Header()] = None,
    after: Annotated[int, Query(ge=0)] = 0,
) -> EventSourceResponse:
    """Server-Sent Events: replays the audit log, then follows live. Resumable via Last-Event-ID."""
    start = int(last_event_id) if last_event_id and last_event_id.isdigit() else after

    async def events() -> AsyncIterator[dict[str, Any]]:
        async for payload in container.runs.stream(run_id, start):
            yield {
                "id": str(payload["id"]),
                "event": "run_event",
                "data": json.dumps(payload, default=str),
            }

    return EventSourceResponse(events(), ping=container.settings.api.sse_ping_seconds)


@router.get("/{run_id}/evidence", response_model=list[EvidenceView])
async def list_evidence(
    run_id: uuid.UUID, container: ContainerDep, _: ApiKeyDep
) -> list[EvidenceView]:
    base = f"{API_PREFIX}/runs/{run_id}/evidence"
    return [EvidenceView.from_row(row, base) for row in await container.runs.evidence(run_id)]


@router.get("/{run_id}/evidence/{evidence_id}")
async def get_evidence_file(
    run_id: uuid.UUID, evidence_id: uuid.UUID, container: ContainerDep, _: ApiKeyDep
) -> FileResponse:
    path = await container.runs.evidence_file(run_id, evidence_id)
    return FileResponse(path, filename=path.name)


@router.post("/{run_id}/input", response_model=RunDetail)
async def answer_question(
    run_id: uuid.UUID, body: AnswerRequest, container: ContainerDep, _: ApiKeyDep
) -> RunDetail:
    return RunDetail.from_state(await container.runs.answer(run_id, body.answer))


@router.post("/{run_id}/cancel", response_model=RunDetail)
async def cancel_run(run_id: uuid.UUID, container: ContainerDep, _: ApiKeyDep) -> RunDetail:
    return RunDetail.from_state(await container.runs.cancel(run_id))
