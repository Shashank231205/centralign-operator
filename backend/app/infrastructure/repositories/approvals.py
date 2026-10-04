import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ApprovalStatus
from app.domain.models import ApprovalResolution, PendingApproval
from app.infrastructure.db.models import ApprovalRow


class ApprovalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def open(self, run_id: uuid.UUID, pending: PendingApproval) -> None:
        self._session.add(
            ApprovalRow(
                id=pending.approval_id,
                run_id=run_id,
                status=ApprovalStatus.PENDING,
                reason=pending.reason,
                rule_ids=pending.rule_ids,
                action=pending.action.model_dump(mode="json"),
                assessment=pending.assessment.model_dump(mode="json"),
            )
        )

    async def get(self, approval_id: uuid.UUID, *, for_update: bool = False) -> ApprovalRow | None:
        query = select(ApprovalRow).where(ApprovalRow.id == approval_id)
        if for_update:
            query = query.with_for_update()
        return await self._session.scalar(query)

    async def pending_for_run(self, run_id: uuid.UUID) -> list[ApprovalRow]:
        query = select(ApprovalRow).where(
            ApprovalRow.run_id == run_id, ApprovalRow.status == ApprovalStatus.PENDING
        )
        return list((await self._session.scalars(query)).all())

    @staticmethod
    def resolve(row: ApprovalRow, status: ApprovalStatus, resolution: ApprovalResolution) -> None:
        row.status = status
        row.comment = resolution.comment or None
        row.edited_payload = resolution.edited_payload
        row.decided_at = datetime.now(UTC)
