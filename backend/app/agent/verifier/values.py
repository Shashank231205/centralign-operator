"""Value comparison across systems: "7,450.00" == 7450.0, "October 28, 2026" == "2026-10-28"."""

import re
from datetime import date, datetime
from typing import Any

_TEMPLATE = re.compile(r"\{\{\s*facts\.([A-Za-z0-9_]+)\s*\}\}")
_AMOUNT = re.compile(r"^[^\d-]*(-?[\d,]+(?:\.\d+)?)[^\d]*$")
_AMOUNT_TOLERANCE = 0.005


class MissingFactError(KeyError):
    pass


def resolve(template: str, facts: dict[str, str]) -> str:
    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in facts:
            raise MissingFactError(name)
        return facts[name]

    return _TEMPLATE.sub(substitute, template)


def referenced_facts(template: str) -> set[str]:
    return set(_TEMPLATE.findall(template))


def values_match(expected: str, actual: Any, date_formats: list[str]) -> bool:
    expected_date, actual_date = (
        parse_date(expected, date_formats),
        parse_date(actual, date_formats),
    )
    if expected_date and actual_date:
        return expected_date == actual_date
    expected_number, actual_number = parse_amount(expected), parse_amount(actual)
    if expected_number is not None and actual_number is not None:
        return abs(expected_number - actual_number) < _AMOUNT_TOLERANCE
    return str(expected).strip().casefold() == str(actual).strip().casefold()


def parse_date(value: Any, formats: list[str]) -> date | None:
    text = str(value).strip()
    for pattern in formats:
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def parse_amount(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    match = _AMOUNT.match(str(value).strip())
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None
