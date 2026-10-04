from uuid import uuid4

from app.core.config import AgentSettings
from app.domain.models import ApprovalGrant

FORMATS = AgentSettings().date_formats
GRANT = ApprovalGrant(
    approval_id=uuid4(),
    system="internal_erp",
    payload={"amount": "7450.00", "due_date": "2026-10-28", "invoice_number": "INV-ACME-1012"},
)


def test_reformatted_values_are_still_the_approved_data() -> None:
    payload = {"amount": "7450", "due_date": "28/10/2026", "invoice_number": "INV-ACME-1012"}
    assert GRANT.covers("internal_erp", payload, FORMATS)


def test_changed_amount_is_not_covered() -> None:
    payload = {"amount": "7400.00", "due_date": "28/10/2026", "invoice_number": "INV-ACME-1012"}
    assert not GRANT.covers("internal_erp", payload, FORMATS)


def test_other_system_or_missing_field_is_not_covered() -> None:
    payload = {"amount": "7450.00", "due_date": "2026-10-28", "invoice_number": "INV-ACME-1012"}
    assert not GRANT.covers("vendor_portal", payload, FORMATS)
    assert not GRANT.covers("internal_erp", {"amount": "7450.00"}, FORMATS)
