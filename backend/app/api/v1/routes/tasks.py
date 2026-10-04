from typing import Annotated

from fastapi import APIRouter, Header, status

from app.api.deps import ApiKeyDep, ContainerDep
from app.api.v1.schemas.runs import CreateTaskRequest, TaskAccepted
from app.core.config import API_PREFIX

router = APIRouter(prefix="/tasks", tags=["tasks"])

_IDEMPOTENCY_KEY_MAX = 200


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=TaskAccepted)
async def create_task(
    body: CreateTaskRequest,
    container: ContainerDep,
    api_key_id: ApiKeyDep,
    idempotency_key: Annotated[str | None, Header(max_length=_IDEMPOTENCY_KEY_MAX)] = None,
) -> TaskAccepted:
    """Queue a natural-language request. Returns immediately; follow progress via events."""
    accepted = await container.tasks.submit(body.request, idempotency_key, api_key_id)
    run_path = f"{API_PREFIX}/runs/{accepted.run_id}"
    return TaskAccepted(
        run_id=accepted.run_id,
        status_url=run_path,
        events_url=f"{run_path}/events",
        replayed=accepted.replayed,
    )
