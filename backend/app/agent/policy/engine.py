"""Decides whether an action may run, needs a human, or is never allowed.

Rules come from company_context/policies.yaml and are evaluated against the exact payload the
action would send (form fields of a browser submit, JSON body of an HTTP write), so approval
is about concrete data, not about what the model claims it is doing.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.agent.understanding.context import Condition, Policies
from app.domain.enums import RiskLevel
from app.domain.models import Assessment

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


class Verdict(StrEnum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    FORBID = "forbid"


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    verdict: Verdict
    rule_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def reason(self) -> str:
        return "; ".join(self.reasons)


class PolicyEngine:
    def __init__(self, policies: Policies) -> None:
        self._policies = policies

    def evaluate(self, assessment: Assessment) -> PolicyDecision:
        payload = {key.lower(): value for key, value in assessment.payload.items()}
        forbidden = [
            rule for rule in self._policies.forbidden_rules if condition_holds(rule.when, payload)
        ]
        if forbidden:
            return PolicyDecision(
                Verdict.FORBID,
                [rule.id for rule in forbidden],
                [rule.description for rule in forbidden],
            )
        if assessment.risk is RiskLevel.READ:
            return PolicyDecision(Verdict.ALLOW)
        matched = [
            rule
            for rule in self._policies.approval_rules
            if assessment.risk.rank >= rule.min_risk.rank
            and (not rule.systems or assessment.system in rule.systems)
            and (rule.when is None or condition_holds(rule.when, payload))
        ]
        if matched:
            return PolicyDecision(
                Verdict.REQUIRE_APPROVAL,
                [rule.id for rule in matched],
                [rule.description for rule in matched],
            )
        return PolicyDecision(Verdict.ALLOW)


def condition_holds(condition: Condition, payload: dict[str, Any]) -> bool:
    value = payload.get(condition.field.lower())
    if condition.op == "exists":
        return value not in (None, "")
    if value in (None, ""):
        return False
    if condition.op == "eq":
        return str(value).strip().lower() == str(condition.value).strip().lower()
    actual, threshold = _number(value), _number(condition.value)
    if actual is None or threshold is None:
        return False
    comparisons = {
        "gt": actual > threshold,
        "gte": actual >= threshold,
        "lt": actual < threshold,
    }
    return comparisons[condition.op]


def _number(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    match = _NUMBER.search(str(value).replace(",", ""))
    return float(match.group(0)) if match else None
