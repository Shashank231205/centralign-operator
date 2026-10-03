from enum import StrEnum


class RunStatus(StrEnum):
    PENDING = "pending"
    UNDERSTANDING = "understanding"
    PLANNING = "planning"
    EXECUTING = "executing"
    REPLANNING = "replanning"
    AWAITING_INPUT = "awaiting_input"
    AWAITING_APPROVAL = "awaiting_approval"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}

    @property
    def is_paused(self) -> bool:
        return self in {RunStatus.AWAITING_INPUT, RunStatus.AWAITING_APPROVAL}


class StepStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


class RiskLevel(StrEnum):
    """How much an action can change the outside world. Ordered from least to most."""

    READ = "read"
    WRITE = "write"
    IRREVERSIBLE = "irreversible"

    @property
    def rank(self) -> int:
        return list(RiskLevel).index(self)

    def max(self, other: "RiskLevel") -> "RiskLevel":
        return self if self.rank >= other.rank else other


class ToolKind(StrEnum):
    BROWSER = "browser"
    FILES = "files"
    HTTP = "http"
    CONTROL = "control"


class FailureKind(StrEnum):
    """Drives recovery: what the runtime does next depends on why an action failed."""

    TRANSIENT = "transient"  # retry with backoff
    STRUCTURAL = "structural"  # re-observe and adapt / replan
    POLICY = "policy"  # escalate to a human
    FATAL = "fatal"  # stop with evidence


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPROVED_WITH_EDITS = "approved_with_edits"


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    APPROVE_WITH_EDITS = "approve_with_edits"


class CriterionKind(StrEnum):
    HTTP_JSON = "http_json"
    FILE = "file"


class EvidenceKind(StrEnum):
    SCREENSHOT = "screenshot"
    FILE = "file"
    EXTRACTED_DATA = "extracted_data"
    VERIFICATION = "verification"
    REPORT = "report"


class MemoryKind(StrEnum):
    LESSON = "lesson"
    FEEDBACK = "feedback"
    OUTCOME = "outcome"
