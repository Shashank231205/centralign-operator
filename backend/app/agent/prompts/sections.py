"""Turns run state and company context into the compact text sections the prompts embed.

Everything the model sees is assembled here, so context size and wording are controlled in
one place.
"""

import json
from datetime import date

from app.agent.understanding.context import CompanyContext, Procedure
from app.agent.verifier.values import referenced_facts
from app.domain.models import CriterionResult, Plan, RunState, StepRecord, SuccessCriterion

NONE = "(none)"
_HISTORY_LINE_CHARS = 220


def base_variables(company: CompanyContext) -> dict[str, str]:
    return {
        "company_name": company.company.name,
        "operator_role": company.company.operator_role,
        "today": date.today().isoformat(),
    }


def systems(company: CompanyContext) -> str:
    blocks = []
    for system in company.systems.values():
        lines = [f"- {system.name}: {system.title} [{system.kind}, access={system.access}]"]
        if system.base_url:
            lines.append(f"  base_url: {system.base_url}")
        if system.credential:
            lines.append(
                f"  credential refs: {system.credential}.username / {system.credential}.password"
                if system.auth != "bearer"
                else "  auth: injected automatically"
            )
        lines.append(f"  purpose: {' '.join(system.purpose.split())}")
        lines += [f"  endpoint: {endpoint}" for endpoint in system.endpoints]
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def procedures(items: list[Procedure]) -> str:
    if not items:
        return NONE
    return "\n\n".join(f"## {item.id}: {item.title}\n{item.body}" for item in items)


def policies(company: CompanyContext) -> str:
    rules = [f"- needs approval: {rule.description}" for rule in company.policies.approval_rules]
    rules += [f"- forbidden: {rule.description}" for rule in company.policies.forbidden_rules]
    return "\n".join(rules) or NONE


def bullet(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else NONE


def facts(values: dict[str, str]) -> str:
    return json.dumps(values, indent=1) if values else NONE


def plan(current: Plan | None) -> str:
    if current is None:
        return NONE
    return "\n".join(
        f"[{step.status}] {step.id}: {step.intent} (tool: {step.tool_hint}, risk: {step.risk})"
        for step in current.steps
    )


def criteria(items: list[SuccessCriterion]) -> str:
    return "\n".join(
        f"- {item.id}: {item.description} :: {item.check.model_dump_json()}" for item in items
    )


def required_facts(state: RunState) -> str:
    if state.plan is None:
        return NONE
    needed: set[str] = set()
    for criterion in state.plan.success_criteria:
        needed |= referenced_facts(criterion.check.model_dump_json())
    missing = sorted(needed - state.facts.keys())
    return ", ".join(missing) if missing else "all recorded"


def history(records: list[StepRecord], window: int) -> str:
    if not records:
        return NONE
    return "\n".join(_history_line(record) for record in records[-window:])


def _history_line(record: StepRecord) -> str:
    outcome = "ok" if record.observation.ok else f"FAILED ({record.observation.error})"
    first_line = record.observation.summary.splitlines()[0] if record.observation.summary else ""
    args = json.dumps(record.action.args)
    line = f"#{record.index} {record.action.tool}({args}) -> {outcome}: {first_line}"
    return line[:_HISTORY_LINE_CHARS]


def latest_observation(records: list[StepRecord]) -> str:
    if not records:
        return "No action taken yet. Start with the first plan step."
    observation = records[-1].observation
    header = "OK" if observation.ok else f"FAILED: {observation.error}"
    return f"{header}\n{observation.summary}"


def verification(results: list[CriterionResult]) -> str:
    if not results:
        return NONE
    return "\n".join(
        f"- {'PASS' if result.passed else 'FAIL'} {result.criterion_id}: {result.detail}"
        for result in results
    )
