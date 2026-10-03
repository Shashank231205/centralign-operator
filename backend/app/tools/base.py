"""Tool contract shared by every capability the operator can use.

A tool declares its argument schema and kind, can *assess* an action before running it (risk,
target system, exact payload — this is what policy evaluates), and *runs* it, always returning
a typed Observation. Tools raise typed errors; they never decide recovery themselves.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Protocol
from uuid import UUID

import httpx
from pydantic import BaseModel

from app.agent.understanding.context import CompanyContext
from app.core.config import SystemCredential
from app.core.errors import PolicyViolationError, ToolInputError
from app.core.rate_limit import BucketSpec, TokenBucketLimiter
from app.core.resilience import BreakerRegistry
from app.domain.enums import EvidenceKind, RiskLevel, ToolKind
from app.domain.models import ArtifactRef, Assessment, Observation
from app.tools.browser.session import BrowserSession


class EvidenceStore(Protocol):
    async def save(
        self, run_id: UUID, name: str, content: bytes, kind: EvidenceKind, description: str
    ) -> ArtifactRef: ...


class Workspace:
    """Per-run folder. Every path the model supplies is resolved strictly inside it."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative: str) -> Path:
        candidate = (self.root / relative.lstrip("/\\")).resolve()
        if not candidate.is_relative_to(self.root):
            raise PolicyViolationError(f"Path '{relative}' is outside the run workspace")
        return candidate

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()


class CredentialStore:
    """Resolves ``<credential>.<field>`` references; the model only ever sees the reference."""

    def __init__(self, credentials: dict[str, SystemCredential]) -> None:
        self._credentials = credentials

    def get(self, name: str) -> SystemCredential:
        if name not in self._credentials:
            raise ToolInputError(f"Unknown credential '{name}'")
        return self._credentials[name]

    def resolve(self, reference: str) -> str:
        name, _, field = reference.partition(".")
        credential = self.get(name)
        if field == "username":
            return credential.username
        if field == "password":
            return credential.password.get_secret_value()
        raise ToolInputError("Secret references look like '<credential>.username|password'")

    def secret_values(self) -> list[str]:
        return [credential.password.get_secret_value() for credential in self._credentials.values()]


class BrowserProvider(Protocol):
    async def session(self) -> BrowserSession: ...


@dataclass(slots=True)
class ToolContext:
    run_id: UUID
    company: CompanyContext
    workspace: Workspace
    evidence: EvidenceStore
    credentials: CredentialStore
    http: httpx.AsyncClient
    browser: BrowserProvider
    limiter: TokenBucketLimiter
    host_bucket: BucketSpec
    host_rate_wait_seconds: float
    breakers: BreakerRegistry
    observation_char_budget: int

    async def throttle_host(self, host: str) -> None:
        """Per-target-host rate limit plus breaker check, shared by browser and HTTP tools."""
        self.breakers.get(f"host:{host}").ensure_closed()
        await self.limiter.wait(f"host:{host}", self.host_bucket, self.host_rate_wait_seconds)


class Tool[ArgsT: BaseModel](ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    kind: ClassVar[ToolKind]
    args_model: type[ArgsT]

    def parse(self, raw: dict[str, Any]) -> ArgsT:
        try:
            return self.args_model.model_validate(raw)
        except ValueError as exc:
            raise ToolInputError(f"Invalid arguments for {self.name}: {exc}") from exc

    async def assess(self, args: ArgsT, ctx: ToolContext) -> Assessment:  # noqa: ARG002
        return Assessment(risk=RiskLevel.READ, description=self.name)

    @abstractmethod
    async def run(self, args: ArgsT, ctx: ToolContext) -> Observation: ...


def ensure_writable(ctx: ToolContext, system: str | None, risk: RiskLevel) -> None:
    """A write aimed at a system the company marks read-only is a policy violation."""
    if system and risk is not RiskLevel.READ:
        info = ctx.company.systems.get(system)
        if info and info.access == "read":
            raise PolicyViolationError(f"System '{system}' is read-only for the operator")


def truncate(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    return f"{text[:budget]}\n…[truncated {len(text) - budget} chars]"
