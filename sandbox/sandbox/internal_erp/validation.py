"""Strict input rules, like a real legacy ERP. The operator has to read and obey error messages."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

DATE_FORMAT_HINT = "DD/MM/YYYY"
PAYMENT_TERMS = ("NET15", "NET30", "NET45", "NET60")
CURRENCIES = ("USD", "EUR", "INR")

_DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_AMOUNT_PATTERN = re.compile(r"^\d+(\.\d{1,2})?$")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class FieldError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


def parse_due_date(raw: str) -> date:
    value = raw.strip()
    if not _DATE_PATTERN.match(value):
        raise FieldError("due_date", f"Due date must be in {DATE_FORMAT_HINT} format.")
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError as exc:
        raise FieldError(
            "due_date", f"Due date is not a real calendar date ({DATE_FORMAT_HINT})."
        ) from exc


def parse_amount(raw: str) -> Decimal:
    value = raw.strip()
    if not _AMOUNT_PATTERN.match(value):
        raise FieldError(
            "amount",
            "Amount must be a plain number without currency symbols or commas, e.g. 1234.50.",
        )
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise FieldError("amount", "Amount is not a valid number.") from exc
    if amount <= 0:
        raise FieldError("amount", "Amount must be greater than zero.")
    return amount


def require_text(field: str, raw: str, label: str) -> str:
    value = raw.strip()
    if not value:
        raise FieldError(field, f"{label} is required.")
    return value


def validate_email(raw: str) -> str:
    value = raw.strip()
    if not _EMAIL_PATTERN.match(value):
        raise FieldError("contact_email", "Contact email is not a valid email address.")
    return value


def validate_choice(field: str, raw: str, allowed: tuple[str, ...], label: str) -> str:
    if raw not in allowed:
        raise FieldError(field, f"{label} must be one of: {', '.join(allowed)}.")
    return raw
