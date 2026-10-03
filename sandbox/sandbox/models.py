"""Two independent schemas: the supplier portal and the buyer's internal ERP never share a DB."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(UTC)


class PortalBase(DeclarativeBase):
    pass


class ErpBase(DeclarativeBase):
    pass


class PortalInvoice(PortalBase):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_name: Mapped[str] = mapped_column(String(120), index=True)
    invoice_number: Mapped[str] = mapped_column(String(40), unique=True)
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(16))
    bill_to: Mapped[str] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text, default="")
    line_items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class ErpVendor(ErpBase):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    contact_name: Mapped[str] = mapped_column(String(120))
    contact_email: Mapped[str] = mapped_column(String(160))
    payment_terms: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    invoices: Mapped[list["ErpInvoice"]] = relationship(back_populates="vendor")


class ErpInvoice(ErpBase):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("vendor_id", "invoice_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    invoice_number: Mapped[str] = mapped_column(String(40))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="unpaid")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    vendor: Mapped[ErpVendor] = relationship(back_populates="invoices", lazy="joined")

    @property
    def is_overdue(self) -> bool:
        return self.status == "unpaid" and self.due_date < date.today()
