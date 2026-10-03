"""What the runtime needs from the outside world. Implemented by the service layer (database,
Redis, evidence storage); the runtime itself stays free of infrastructure."""

from typing import Protocol

from app.domain.events import DomainEvent
from app.domain.models import ArtifactRef, PendingApproval, RunState, StepRecord


class RunRecorder(Protocol):
    async def checkpoint(self, state: RunState) -> None:
        """Durably persist the full run state (the resume point)."""

    async def emit(self, state: RunState, event: DomainEvent) -> None:
        """Append to the audit log and publish to live subscribers."""

    async def record_step(self, state: RunState, record: StepRecord) -> None:
        """Persist one executed action with its observation."""

    async def add_evidence(self, state: RunState, artifact: ArtifactRef) -> None:
        """Index a stored artifact (screenshot, file, report) against the run."""

    async def open_approval(self, state: RunState, pending: PendingApproval) -> None:
        """Create the approval request a human will resolve."""

    async def cancel_requested(self, state: RunState) -> bool:
        """True if someone asked to cancel this run."""


class CompanyMemory(Protocol):
    async def recall(self, query: str, limit: int) -> list[str]:
        """Lessons and feedback from earlier runs relevant to ``query``."""

    async def learn(self, lessons: list[str], source_run: str) -> list[str]:
        """Store new lessons; returns those actually added (deduplicated)."""
