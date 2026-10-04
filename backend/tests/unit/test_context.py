from pathlib import Path

import pytest

from app.agent.understanding.context import ContextLoader

CONTEXT_DIR = Path(__file__).resolve().parents[3] / "company_context"
VARIABLES = {"SANDBOX_PORTAL_URL": "http://portal.test", "SANDBOX_ERP_URL": "http://erp.test"}


def test_loads_systems_with_resolved_urls_and_allowlist() -> None:
    company = ContextLoader(CONTEXT_DIR, VARIABLES).load()
    assert company.systems["internal_erp_api"].base_url == "http://erp.test/api"
    assert company.allowed_hosts == {"portal.test", "erp.test"}


def test_most_specific_system_wins_for_a_url() -> None:
    company = ContextLoader(CONTEXT_DIR, VARIABLES).load()
    system = company.system_for_url("http://erp.test/api/invoices")
    assert system is not None and system.name == "internal_erp_api"


def test_procedure_retrieval_ranks_by_request_words() -> None:
    company = ContextLoader(CONTEXT_DIR, VARIABLES).load()
    top = company.retrieve_procedures("export overdue invoices to a csv report", top_k=1)
    assert top[0].id == "overdue-report"


def test_missing_variable_fails_fast() -> None:
    with pytest.raises(ValueError, match="SANDBOX_ERP_URL"):
        ContextLoader(CONTEXT_DIR, {"SANDBOX_PORTAL_URL": "http://p"}).load()
