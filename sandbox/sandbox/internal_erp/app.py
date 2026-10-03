"""Ledgerly: the buyer's internal ERP (vendors, payable invoices) with a strict legacy-style UI."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sandbox.chaos import ChaosEngine
from sandbox.config import SandboxSettings, get_settings
from sandbox.internal_erp import api
from sandbox.internal_erp.validation import (
    CURRENCIES,
    PAYMENT_TERMS,
    FieldError,
    parse_amount,
    parse_due_date,
    require_text,
    validate_choice,
    validate_email,
)
from sandbox.models import ErpInvoice, ErpVendor
from sandbox.web import (
    CurrentUser,
    DbSession,
    build_app,
    chaos_of,
    credentials_match,
    render,
    safe_next,
    sign_in,
)

ERP_DB_FILE = "erp.db"
HOME = "/invoices"
STATUS_FILTERS = ("all", "unpaid", "overdue", "paid")

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, next: str = HOME) -> Response:  # noqa: A002
    return render(request, "login.html", next=next, error=None, product="Ledgerly ERP")


@router.post("/login", response_model=None)
async def login(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    next: Annotated[str, Form()] = HOME,  # noqa: A002
) -> Response:
    settings: SandboxSettings = request.app.state.settings
    valid = credentials_match(username, settings.sandbox.erp_username) & credentials_match(
        password, settings.sandbox.erp_password.get_secret_value()
    )
    if not valid:
        return render(
            request,
            "login.html",
            401,
            next=next,
            error="Invalid username or password.",
            product="Ledgerly ERP",
        )
    sign_in(request, username)
    return RedirectResponse(safe_next(next, HOME), status_code=303)


@router.get("/")
async def home() -> RedirectResponse:
    return RedirectResponse(HOME, status_code=303)


@router.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/vendors", response_class=HTMLResponse)
async def list_vendors(request: Request, session: DbSession, user: CurrentUser) -> Response:
    vendors = (await session.scalars(select(ErpVendor).order_by(ErpVendor.name))).all()
    return render(request, "vendors.html", vendors=vendors, user=user)


@router.get("/vendors/new", response_class=HTMLResponse)
async def new_vendor_form(request: Request, user: CurrentUser) -> Response:
    return _vendor_form(request, user, values={}, error=None)


@router.post("/vendors", response_model=None)
async def create_vendor(
    request: Request,
    session: DbSession,
    user: CurrentUser,
    name: Annotated[str, Form()] = "",
    contact_name: Annotated[str, Form()] = "",
    contact_email: Annotated[str, Form()] = "",
    payment_terms: Annotated[str, Form()] = "",
) -> Response:
    values = {
        "name": name,
        "contact_name": contact_name,
        "contact_email": contact_email,
        "payment_terms": payment_terms,
    }
    try:
        vendor = ErpVendor(
            name=require_text("name", name, "Vendor name"),
            contact_name=require_text("contact_name", contact_name, "Contact name"),
            contact_email=validate_email(contact_email),
            payment_terms=validate_choice(
                "payment_terms", payment_terms, PAYMENT_TERMS, "Payment terms"
            ),
        )
        session.add(vendor)
        await session.commit()
    except FieldError as error:
        return _vendor_form(request, user, values, error.message, status_code=422)
    except IntegrityError:
        await session.rollback()
        return _vendor_form(
            request, user, values, f"Vendor '{name}' already exists.", status_code=409
        )
    return _created(chaos_of(request), f"/vendors?created={vendor.id}")


@router.get("/invoices", response_class=HTMLResponse)
async def list_invoices(
    request: Request, session: DbSession, user: CurrentUser, status: str = "all", created: int = 0
) -> Response:
    invoices = (
        (await session.scalars(api.invoice_query("", "", "" if status == "all" else status)))
        .unique()
        .all()
    )
    return render(
        request,
        "invoices.html",
        invoices=invoices,
        status=status,
        filters=STATUS_FILTERS,
        created=created,
        user=user,
    )


@router.get("/invoices/new", response_class=HTMLResponse)
async def new_invoice_form(request: Request, session: DbSession, user: CurrentUser) -> Response:
    return await _invoice_form(request, session, user, values={}, error=None)


@router.post("/invoices", response_model=None)
async def create_invoice(
    request: Request,
    session: DbSession,
    user: CurrentUser,
    vendor_id: Annotated[str, Form()] = "",
    invoice_number: Annotated[str, Form()] = "",
    amount: Annotated[str, Form()] = "",
    currency: Annotated[str, Form()] = "",
    due_date: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
) -> Response:
    values = {
        "vendor_id": vendor_id,
        "invoice_number": invoice_number,
        "amount": amount,
        "currency": currency,
        "due_date": due_date,
        "notes": notes,
    }
    try:
        invoice = ErpInvoice(
            vendor_id=await _resolve_vendor_id(session, vendor_id),
            invoice_number=require_text("invoice_number", invoice_number, "Invoice number"),
            amount=parse_amount(amount),
            currency=validate_choice("currency", currency, CURRENCIES, "Currency"),
            due_date=parse_due_date(due_date),
            notes=notes.strip(),
        )
        session.add(invoice)
        await session.commit()
    except FieldError as error:
        return await _invoice_form(request, session, user, values, error.message, status_code=422)
    except IntegrityError:
        await session.rollback()
        message = f"Invoice {invoice_number} is already recorded for this vendor."
        return await _invoice_form(request, session, user, values, message, status_code=409)
    return _created(chaos_of(request), f"/invoices?created={invoice.id}")


async def _resolve_vendor_id(session: AsyncSession, raw: str) -> int:
    if not raw.isdigit() or await session.get(ErpVendor, int(raw)) is None:
        raise FieldError("vendor_id", "Select a vendor.")
    return int(raw)


def _created(chaos: ChaosEngine, location: str) -> Response:
    """The write is committed; under the duplicate trap the acknowledgement is 'lost'."""
    if chaos.consume_ack_trap():
        raise HTTPException(status_code=502, detail="Bad gateway: upstream did not respond")
    return RedirectResponse(location, status_code=303)


def _vendor_form(
    request: Request, user: str, values: dict[str, str], error: str | None, status_code: int = 200
) -> Response:
    return render(
        request,
        "vendor_form.html",
        status_code,
        values=values,
        error=error,
        payment_terms=PAYMENT_TERMS,
        user=user,
    )


async def _invoice_form(
    request: Request,
    session: AsyncSession,
    user: str,
    values: dict[str, str],
    error: str | None,
    status_code: int = 200,
) -> Response:
    vendors = (await session.scalars(select(ErpVendor).order_by(ErpVendor.name))).all()
    return render(
        request,
        "invoice_form.html",
        status_code,
        values=values,
        error=error,
        vendors=vendors,
        currencies=CURRENCIES,
        user=user,
    )


def create_app() -> FastAPI:
    app = build_app(
        title="Ledgerly ERP",
        settings=get_settings(),
        cookie_name="ledgerly_session",
        package_dir=Path(__file__).parent,
        db_file=ERP_DB_FILE,
    )
    app.include_router(router)
    app.include_router(api.router)
    return app
