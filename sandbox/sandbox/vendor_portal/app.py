"""SupplyLink: a supplier portal where the buyer's AP team views and downloads vendor invoices.

Amounts and due dates are only in the PDFs, so completing invoice tasks requires a real
download-and-extract step rather than scraping a table.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sandbox.config import SandboxSettings, get_settings
from sandbox.models import PortalInvoice
from sandbox.vendor_portal.pdf import render_invoice_pdf
from sandbox.web import (
    CurrentUser,
    DbSession,
    build_app,
    credentials_match,
    render,
    safe_next,
    sign_in,
)

PORTAL_DB_FILE = "portal.db"
HOME = "/invoices"

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, next: str = HOME) -> Response:  # noqa: A002
    return render(request, "login.html", next=next, error=None, product="SupplyLink")


@router.post("/login", response_model=None)
async def login(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    next: Annotated[str, Form()] = HOME,  # noqa: A002
) -> Response:
    settings: SandboxSettings = request.app.state.settings
    valid = credentials_match(username, settings.sandbox.portal_username) & credentials_match(
        password, settings.sandbox.portal_password.get_secret_value()
    )
    if not valid:
        return render(
            request,
            "login.html",
            401,
            next=next,
            error="Invalid email or password.",
            product="SupplyLink",
        )
    sign_in(request, username)
    return RedirectResponse(safe_next(next, HOME), status_code=303)


@router.get("/")
async def home() -> RedirectResponse:
    return RedirectResponse(HOME, status_code=303)


@router.get("/invoices", response_class=HTMLResponse)
async def list_invoices(
    request: Request, session: DbSession, user: CurrentUser, vendor: str = ""
) -> Response:
    query = select(PortalInvoice).order_by(PortalInvoice.vendor_name, PortalInvoice.id)
    if vendor:
        query = query.where(PortalInvoice.vendor_name.ilike(f"%{vendor}%"))
    invoices = (await session.scalars(query)).all()
    return render(request, "invoices.html", invoices=invoices, vendor=vendor, user=user)


@router.get("/invoices/{invoice_number}", response_class=HTMLResponse)
async def invoice_detail(
    request: Request, invoice_number: str, session: DbSession, user: CurrentUser
) -> Response:
    invoice = await _get_invoice(session, invoice_number)
    return render(request, "invoice_detail.html", invoice=invoice, user=user)


@router.get("/invoices/{invoice_number}/pdf")
async def invoice_pdf(invoice_number: str, session: DbSession, _: CurrentUser) -> Response:
    invoice = await _get_invoice(session, invoice_number)
    return Response(
        render_invoice_pdf(invoice),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{invoice_number}.pdf"'},
    )


@router.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


async def _get_invoice(session: AsyncSession, invoice_number: str) -> PortalInvoice:
    invoice = await session.scalar(
        select(PortalInvoice).where(PortalInvoice.invoice_number == invoice_number)
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


def create_app() -> FastAPI:
    app = build_app(
        title="SupplyLink Vendor Portal",
        settings=get_settings(),
        cookie_name="supplylink_session",
        package_dir=Path(__file__).parent,
        db_file=PORTAL_DB_FILE,
    )
    app.include_router(router)
    return app
