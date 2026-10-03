"""Loads company_context/ (systems, policies, procedures) and retrieves what a request needs.

This is what makes the operator *this company's* employee: every task-specific fact lives in
these files, never in agent code. Files are re-read when they change on disk.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import yaml
from app.domain.enums import RiskLevel
from pydantic import BaseModel, Field

_ENV_REFERENCE = re.compile(r"\$\{([A-Z0-9_]+)\}")
_FRONT_MATTER = re.compile(r"^---\n(?P<meta>.*?)\n---\n(?P<body>.*)$", re.DOTALL)
_WORD = re.compile(r"[a-z0-9]+")


class SystemInfo(BaseModel):
    name: str
    title: str
    kind: Literal["web_app", "http_api", "files"]
    base_url: str | None = None
    credential: str | None = None
    auth: Literal["bearer", "form"] | None = None
    access: Literal["read", "read_write"]
    purpose: str
    endpoints: list[str] = Field(default_factory=list)

    @property
    def host(self) -> str | None:
        return urlparse(self.base_url).netloc if self.base_url else None


class Condition(BaseModel):
    field: str
    op: Literal["gt", "gte", "lt", "eq", "exists"]
    value: Any = None


class ApprovalRule(BaseModel):
    id: str
    description: str
    systems: list[str] = Field(default_factory=list)
    min_risk: RiskLevel = RiskLevel.WRITE
    when: Condition | None = None


class ForbiddenRule(BaseModel):
    id: str
    description: str
    when: Condition


class Policies(BaseModel):
    extra_allowed_hosts: list[str] = Field(default_factory=list)
    approval_rules: list[ApprovalRule] = Field(default_factory=list)
    forbidden_rules: list[ForbiddenRule] = Field(default_factory=list)


class Procedure(BaseModel):
    id: str
    title: str
    keywords: list[str]
    systems: list[str]
    body: str


class CompanyProfile(BaseModel):
    name: str
    description: str
    operator_role: str
    currency_default: str


@dataclass(frozen=True, slots=True)
class CompanyContext:
    company: CompanyProfile
    systems: dict[str, SystemInfo]
    policies: Policies
    procedures: list[Procedure]

    @property
    def allowed_hosts(self) -> set[str]:
        hosts = {system.host for system in self.systems.values() if system.host}
        return hosts | set(self.policies.extra_allowed_hosts)

    def system_for_url(self, url: str) -> SystemInfo | None:
        """Most specific system whose base URL prefixes ``url`` (API before web UI)."""
        matches = [
            system
            for system in self.systems.values()
            if system.base_url and url.startswith(system.base_url.rstrip("/"))
        ]
        return max(matches, key=lambda system: len(system.base_url or ""), default=None)

    def retrieve_procedures(self, request: str, top_k: int) -> list[Procedure]:
        """Keyword-overlap ranking; small, deterministic and explainable for a handful of SOPs."""
        words = set(_WORD.findall(request.lower()))
        scored = []
        for procedure in self.procedures:
            vocabulary = set(procedure.keywords) | set(_WORD.findall(procedure.title.lower()))
            score = len(words & vocabulary)
            if score:
                scored.append((score, procedure))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [procedure for _, procedure in scored[:top_k]]


class ContextLoader:
    def __init__(self, directory: Path, variables: Mapping[str, str]) -> None:
        self._directory = directory
        self._variables = variables
        self._cached: CompanyContext | None = None
        self._fingerprint: tuple[float, ...] = ()

    def load(self) -> CompanyContext:
        fingerprint = tuple(path.stat().st_mtime for path in sorted(self._directory.rglob("*")))
        if self._cached is None or fingerprint != self._fingerprint:
            self._cached = self._read()
            self._fingerprint = fingerprint
        return self._cached

    def _read(self) -> CompanyContext:
        profile = _yaml(self._directory / "profile.yaml")
        systems = {
            name: SystemInfo(name=name, **_resolve_env(spec, self._variables))
            for name, spec in profile["systems"].items()
        }
        return CompanyContext(
            company=CompanyProfile(**profile["company"]),
            systems=systems,
            policies=Policies(**_yaml(self._directory / "policies.yaml")),
            procedures=[
                _procedure(path) for path in sorted((self._directory / "procedures").glob("*.md"))
            ],
        )


def _yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError(f"{path} must contain a mapping")
    return loaded


def _resolve_env(value: Any, variables: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return _ENV_REFERENCE.sub(lambda match: _require(match.group(1), variables), value)
    if isinstance(value, dict):
        return {key: _resolve_env(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_env(item, variables) for item in value]
    return value


def _require(name: str, variables: Mapping[str, str]) -> str:
    value = variables.get(name)
    if not value:
        raise ValueError(f"company_context references ${{{name}}} but it is not set")
    return value


def _procedure(path: Path) -> Procedure:
    match = _FRONT_MATTER.match(path.read_text(encoding="utf-8").replace("\r\n", "\n"))
    if not match:
        raise ValueError(f"Procedure {path.name} needs YAML front matter")
    meta = yaml.safe_load(match["meta"])
    return Procedure(**meta, body=match["body"].strip())
