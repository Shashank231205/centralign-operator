"""Operational metrics computed from run checkpoints (no separate metrics store needed)."""

from typing import Any

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import RunRow


def _counter(name: str) -> Any:
    return cast(RunRow.state["counters"][name].astext, Integer)


class MetricsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def by_status(self) -> list[dict[str, Any]]:
        duration = func.extract(
            "epoch", func.coalesce(RunRow.finished_at, func.now()) - RunRow.created_at
        )
        query = select(
            RunRow.status,
            func.count().label("runs"),
            func.avg(duration).label("avg_duration_seconds"),
            func.avg(_counter("steps")).label("avg_steps"),
            func.sum(_counter("retries")).label("total_retries"),
            func.sum(_counter("replans")).label("total_replans"),
            func.sum(_counter("llm_calls")).label("total_llm_calls"),
            func.sum(_counter("prompt_tokens") + _counter("completion_tokens")).label(
                "total_llm_tokens"
            ),
        ).group_by(RunRow.status)
        rows = (await self._session.execute(query)).mappings().all()
        return [
            {
                key: (round(float(value), 2) if isinstance(value, float) else value)
                for key, value in row.items()
            }
            for row in rows
        ]
