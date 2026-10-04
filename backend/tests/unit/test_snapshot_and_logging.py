from app.core.logging import redact
from app.tools.browser.snapshot import ElementInfo, FormInfo, PageSnapshot


def test_snapshot_render_lists_refs_messages_and_submit_buttons() -> None:
    snapshot = PageSnapshot(
        url="http://erp/invoices/new",
        title="Enter invoice",
        alerts=["Due date must be in DD/MM/YYYY format."],
        elements=[
            ElementInfo(ref="e1", tag="input", type="text", label="Amount", value="7450.00"),
            ElementInfo(ref="e2", tag="button", type="submit", label="Save invoice", submits=True),
        ],
        forms=[FormInfo(index=0, method="POST", action="http://erp/invoices", fields={})],
        status=422,
    )
    text = snapshot.render(budget=2000)
    assert "MESSAGE: Due date must be in DD/MM/YYYY format." in text
    assert "[e1] input[text] 'Amount' = '7450.00'" in text
    assert "(submits form)" in text
    assert "HTTP STATUS: 422" in text


def test_snapshot_render_respects_budget() -> None:
    snapshot = PageSnapshot(url="u", title="t", text="x" * 10_000)
    assert len(snapshot.render(budget=500)) <= 500


def test_redaction_masks_secret_fields_and_bare_keys() -> None:
    line = (
        '{"password": "hunter2", "authorization": "Bearer abc.def", '
        '"key": "gsk_1234567890abcdefXYZ"}'
    )
    cleaned = redact(line)
    assert "hunter2" not in cleaned
    assert "abc.def" not in cleaned
    assert "gsk_1234567890abcdefXYZ" not in cleaned
