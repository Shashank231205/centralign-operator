import pytest

from app.core.config import AgentSettings
from app.domain.values import (
    MissingFactError,
    parse_amount,
    referenced_facts,
    resolve,
    values_match,
)

FORMATS = AgentSettings().date_formats


@pytest.mark.parametrize(
    ("expected", "actual"),
    [
        ("7450.00", 7450.0),
        ("7,450.00", "7450"),
        ("2026-10-28", "28/10/2026"),
        ("October 28, 2026", "2026-10-28"),
        ("Acme Corp", "acme corp "),
    ],
)
def test_values_match_across_formats(expected: str, actual: object) -> None:
    assert values_match(expected, actual, FORMATS)


@pytest.mark.parametrize(
    ("expected", "actual"),
    [("7450.00", 7450.5), ("2026-10-28", "2026-10-27"), ("Acme Corp", "Acme Logistics")],
)
def test_values_differ(expected: str, actual: object) -> None:
    assert not values_match(expected, actual, FORMATS)


def test_resolve_substitutes_facts_and_reports_missing_ones() -> None:
    assert resolve("{{facts.invoice_number}}", {"invoice_number": "INV-1"}) == "INV-1"
    with pytest.raises(MissingFactError):
        resolve("{{ facts.amount }}", {})


def test_referenced_facts() -> None:
    assert referenced_facts('{"a": "{{facts.x}}", "b": "{{ facts.y }}"}') == {"x", "y"}


def test_parse_amount_handles_currency_text() -> None:
    assert parse_amount("USD 1,250.50") == 1250.5
    assert parse_amount("n/a") is None
