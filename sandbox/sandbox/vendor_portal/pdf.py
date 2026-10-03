"""Renders a supplier invoice as a real PDF so the operator must download and parse a document."""

from fpdf import FPDF

from sandbox.models import PortalInvoice
from sandbox.web import money


def render_invoice_pdf(invoice: PortalInvoice) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, invoice.vendor_name, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, "TAX INVOICE", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    _key_values(
        pdf,
        [
            ("Invoice number", invoice.invoice_number),
            ("Issue date", invoice.issue_date.strftime("%B %d, %Y")),
            ("Payment due", invoice.due_date.strftime("%B %d, %Y")),
            ("Bill to", invoice.bill_to),
        ],
    )
    pdf.ln(4)
    _line_items(pdf, invoice)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(
        0,
        10,
        f"Total due: {invoice.currency} {money(invoice.amount)}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    if invoice.notes:
        pdf.ln(4)
        pdf.set_font("Helvetica", "I", 9)
        pdf.multi_cell(0, 5, f"Notes: {invoice.notes}")
    return bytes(pdf.output())


def _key_values(pdf: FPDF, rows: list[tuple[str, str]]) -> None:
    for key, value in rows:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(40, 7, key)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, value, new_x="LMARGIN", new_y="NEXT")


def _line_items(pdf: FPDF, invoice: PortalInvoice) -> None:
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(110, 8, "Description", border=1)
    pdf.cell(25, 8, "Qty", border=1)
    pdf.cell(45, 8, "Line total", border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for item in invoice.line_items:
        pdf.cell(110, 8, str(item["description"]), border=1)
        pdf.cell(25, 8, str(item["quantity"]), border=1)
        pdf.cell(45, 8, money(item["total"]), border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
