"""Read-only JSON API used for independent verification and reporting (bearer token auth)."""

import hmac
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import Select, select

from sandbox.config import SandboxSettings
from sandbox.models import ErpInvoice, ErpVendor
from sandbox.web import DbSession

STATUS_OVERDUE = "overdue"


def require_token(request: Request, authorization: Annotated[str, Header()] = "") -> None:
    settings: SandboxSettings = request.app.state.settings
    expected = f"Bearer {settings.sandbox.erp_api_token.get_secret_value()}"
    if not hmac.compare_digest(authorization.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")


router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


@router.get("/vendors")
async def list_vendors(session: DbSession, name: str = "") -> dict[str, Any]:
    query = select(ErpVendor).order_by(ErpVendor.name)
    if name:
        query = query.where(ErpVendor.name.ilike(name))
    vendors = (await session.scalars(query)).all()
    return {"count": len(vendors), "items": [vendor_json(vendor) for vendor in vendors]}


@router.get("/invoices")
async def list_invoices(
    session: DbSession, vendor: str = "", invoice_number: str = "", status: str = ""
) -> dict[str, Any]:
    invoices = (await session.scalars(invoice_query(vendor, invoice_number, status))).unique().all()
    return {"count": len(invoices), "items": [invoice_json(invoice) for invoice in invoices]}


def invoice_query(vendor: str, invoice_number: str, status: str) -> Select[ErpInvoice]:
    query = select(ErpInvoice).join(ErpInvoice.vendor).order_by(ErpInvoice.due_date)
    if vendor:
        query = query.where(ErpVendor.name.ilike(vendor))
    if invoice_number:
        query = query.where(ErpInvoice.invoice_number == invoice_number)
    if status == STATUS_OVERDUE:
        query = query.where(ErpInvoice.status == "unpaid", ErpInvoice.due_date < date.today())
    elif status:
        query = query.where(ErpInvoice.status == status)
    return query


def vendor_json(vendor: ErpVendor) -> dict[str, Any]:
    return {
        "id": vendor.id,
        "name": vendor.name,
        "contact_name": vendor.contact_name,
        "contact_email": vendor.contact_email,
        "payment_terms": vendor.payment_terms,
    }


def invoice_json(invoice: ErpInvoice) -> dict[str, Any]:
    return {
        "id": invoice.id,
        "vendor": invoice.vendor.name,
        "invoice_number": invoice.invoice_number,
        "amount": float(invoice.amount),
        "currency": invoice.currency,
        "due_date": invoice.due_date.isoformat(),
        "status": invoice.status,
        "overdue": invoice.is_overdue,
    }
