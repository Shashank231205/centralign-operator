import uuid

from fastapi import APIRouter

from app.api.deps import ApiKeyDep, ContainerDep
from app.api.v1.schemas.runs import ApprovalDecisionRequest, RunDetail
from app.core.errors import AppError
from app.domain.enums import ApprovalDecision
from app.domain.models import ApprovalResolution

router = APIRouter(prefix="/approvals", tags=["approvals"])


class EditsRequiredError(AppError):
    status_code = 422
    code = "edits_required"


@router.post("/{approval_id}", response_model=RunDetail)
async def resolve_approval(
    approval_id: uuid.UUID, body: ApprovalDecisionRequest, container: ContainerDep, _: ApiKeyDep
) -> RunDetail:
    """Approve, reject, or approve with edited values. The run resumes automatically."""
    if body.decision is ApprovalDecision.APPROVE_WITH_EDITS and not body.edited_payload:
        raise EditsRequiredError("approve_with_edits requires edited_payload")
    resolution = ApprovalResolution(
        decision=body.decision, comment=body.comment, edited_payload=body.edited_payload
    )
    return RunDetail.from_state(await container.approvals.resolve(approval_id, resolution))
