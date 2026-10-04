from datetime import date
from decimal import Decimal

import pytest

from sandbox.chaos import ChaosEngine
from sandbox.config import ChaosSettings
from sandbox.internal_erp.validation import FieldError, parse_amount, parse_due_date


def test_due_date_requires_dd_mm_yyyy() -> None:
    assert parse_due_date("28/10/2026") == date(2026, 10, 28)
    with pytest.raises(FieldError, match="DD/MM/YYYY"):
        parse_due_date("2026-10-28")
    with pytest.raises(FieldError, match="real calendar date"):
        parse_due_date("31/02/2026")


def test_amount_must_be_plain_number() -> None:
    assert parse_amount("7450.00") == Decimal("7450.00")
    with pytest.raises(FieldError, match="plain number"):
        parse_amount("7,450.00")
    with pytest.raises(FieldError, match="greater than zero"):
        parse_amount("0")


def test_chaos_is_deterministic_for_a_seed() -> None:
    settings = ChaosSettings(enabled=True, seed=7, error_rate=0.5)
    engine_a, engine_b = ChaosEngine(settings), ChaosEngine(settings)
    assert [engine_a.should_fail() for _ in range(20)] == [
        engine_b.should_fail() for _ in range(20)
    ]


def test_chaos_disabled_never_fails() -> None:
    engine = ChaosEngine(ChaosSettings(enabled=False, error_rate=1.0))
    assert not any(engine.should_fail() for _ in range(50))
    assert engine.render_delay_ms == 0
    assert engine.label("save_invoice") == "Save invoice"


def test_duplicate_trap_fires_exactly_once() -> None:
    engine = ChaosEngine(ChaosSettings(enabled=True, duplicate_trap=True))
    assert engine.consume_ack_trap()
    assert not engine.consume_ack_trap()
