from typing import Any

from fastapi import APIRouter

from app.api.deps import ApiKeyDep, ContainerDep
from app.infrastructure.repositories.metrics import MetricsRepository

router = APIRouter(prefix="/metrics", tags=["observability"])


@router.get("")
async def metrics(container: ContainerDep, _: ApiKeyDep) -> dict[str, Any]:
    """Run outcomes, durations, steps, retries, re-plans and LLM usage, grouped by status."""
    async with container.database.session() as session:
        by_status = await MetricsRepository(session).by_status()
    return {"runs_by_status": by_status}
