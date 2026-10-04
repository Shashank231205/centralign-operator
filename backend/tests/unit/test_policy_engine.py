from app.agent.policy.engine import PolicyEngine, Verdict, condition_holds
from app.agent.understanding.context import ApprovalRule, Condition, ForbiddenRule, Policies
from app.domain.enums import RiskLevel
from app.domain.models import Assessment

POLICIES = Policies(
    approval_rules=[
        ApprovalRule(
            id="high_value",
            description="Payables above 5,000 need approval",
            systems=["internal_erp"],
            min_risk=RiskLevel.WRITE,
            when=Condition(field="amount", op="gt", value=5000),
        ),
        ApprovalRule(id="irreversible", description="Always ask", min_risk=RiskLevel.IRREVERSIBLE),
    ],
    forbidden_rules=[
        ForbiddenRule(
            id="no_paid",
            description="Never mark paid",
            when=Condition(field="status", op="eq", value="paid"),
        )
    ],
)


def assess(risk: RiskLevel, system: str = "internal_erp", **payload: object) -> Assessment:
    return Assessment(risk=risk, system=system, payload=payload)


def test_reads_are_allowed_without_rules() -> None:
    assert PolicyEngine(POLICIES).evaluate(assess(RiskLevel.READ)).verdict is Verdict.ALLOW


def test_high_value_write_requires_approval_using_the_actual_payload() -> None:
    decision = PolicyEngine(POLICIES).evaluate(assess(RiskLevel.WRITE, amount="7,450.00"))
    assert decision.verdict is Verdict.REQUIRE_APPROVAL
    assert decision.rule_ids == ["high_value"]


def test_low_value_write_is_allowed() -> None:
    decision = PolicyEngine(POLICIES).evaluate(assess(RiskLevel.WRITE, amount="980.00"))
    assert decision.verdict is Verdict.ALLOW


def test_rule_scoped_to_other_system_does_not_apply() -> None:
    decision = PolicyEngine(POLICIES).evaluate(
        assess(RiskLevel.WRITE, system="workspace", amount="9000")
    )
    assert decision.verdict is Verdict.ALLOW


def test_forbidden_beats_everything_even_for_reads() -> None:
    decision = PolicyEngine(POLICIES).evaluate(assess(RiskLevel.READ, status="PAID"))
    assert decision.verdict is Verdict.FORBID


def test_irreversible_always_needs_approval() -> None:
    decision = PolicyEngine(POLICIES).evaluate(assess(RiskLevel.IRREVERSIBLE, system="any"))
    assert decision.verdict is Verdict.REQUIRE_APPROVAL


def test_condition_operators() -> None:
    assert condition_holds(Condition(field="email", op="exists"), {"email": "a@b.c"})
    assert not condition_holds(Condition(field="email", op="exists"), {"email": ""})
    assert condition_holds(Condition(field="amount", op="gte", value=10), {"amount": "USD 10"})
    assert not condition_holds(Condition(field="amount", op="lt", value=10), {"amount": "abc"})
