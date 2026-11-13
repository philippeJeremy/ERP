"""Routes HTTP du module facturation."""

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import Field
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.db import get_db
from app.modules.auth.public import require
from app.modules.billing import accounting, invoices, payments, pdf, suppliers
from app.modules.billing.common import Invalid, get_settings, save_settings
from app.modules.billing.schemas import (
    Allocate,
    Approve,
    CreditNoteIn,
    CustomerAccount,
    CustomerToBill,
    EntriesPage,
    FromDeliveries,
    InvoiceCreate,
    InvoicePage,
    InvoiceRead,
    InvoiceUpdate,
    LineIn,
    PaymentIn,
    PaymentPage,
    PaymentRead,
    Receivables,
    ReceptionToBill,
    SettingsIn,
    SettingsRead,
    SupplierInvoiceCreate,
    SupplierInvoicePage,
    SupplierInvoiceRead,
    SupplierInvoiceUpdate,
    SupplierLineIn,
    SupplierPaymentIn,
)
from app.shared.schemas import Schema

router = APIRouter(prefix="/billing", tags=["Facturation"])

READ = Depends(require("billing:read"))
MANAGE = Depends(require("billing:manage"))
PAYMENTS = Depends(require("billing:payments"))
SUPPLIERS = Depends(require("billing:suppliers"))
ACCOUNTING = Depends(require("billing:accounting"))


def _file(content: bytes | str, name: str, media: str, inline: bool = True) -> Response:
    disposition = "inline" if inline else "attachment"
    return Response(
        content,
        media_type=media,
        headers={"Content-Disposition": f'{disposition}; filename="{name}"'},
    )


class CreditApply(Schema):
    invoice_id: int
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)


# --- Réglages ---------------------------------------------------------------------------


@router.get("/settings", response_model=SettingsRead, dependencies=[READ])
def read_settings(db: Session = Depends(get_db)):
    return get_settings(db)


@router.put("/settings", response_model=SettingsRead, dependencies=[ACCOUNTING])
def write_settings(data: SettingsIn, db: Session = Depends(get_db)):
    return save_settings(db, data.model_dump())


# --- Factures client --------------------------------------------------------------------


@router.get("/to-invoice", response_model=list[CustomerToBill], dependencies=[READ])
def to_invoice(customer_id: int | None = None, db: Session = Depends(get_db)):
    """Bons de livraison pas encore facturés, regroupés par client."""
    return invoices.to_bill(db, customer_id)


@router.post("/invoices/from-deliveries", response_model=list[InvoiceRead], dependencies=[MANAGE])
def from_deliveries(
    data: FromDeliveries, db: Session = Depends(get_db), ctx: RequestContext = MANAGE
):
    return invoices.from_deliveries(db, ctx, data)


@router.get("/invoices", response_model=InvoicePage, dependencies=[READ])
def list_invoices(
    kind: Literal["facture", "avoir"] | None = None,
    status: Literal["brouillon", "emise"] | None = None,
    payment: Literal["a_payer", "en_retard", "payee"] | None = None,
    customer_id: int | None = None,
    q: str | None = Query(None, max_length=100),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return invoices.list_invoices(
        db, kind=kind, status=status, payment=payment, customer_id=customer_id, q=q,
        limit=limit, offset=offset,
    )  # fmt: skip


@router.post("/invoices", response_model=InvoiceRead, status_code=201, dependencies=[MANAGE])
def create_invoice(data: InvoiceCreate, db: Session = Depends(get_db)):
    """Facture libre (prestations sans livraison)."""
    return invoices.create(db, data)


@router.get("/invoices/{invoice_id}", response_model=InvoiceRead, dependencies=[READ])
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    return invoices.get_invoice(db, invoice_id)


@router.patch("/invoices/{invoice_id}", response_model=InvoiceRead, dependencies=[MANAGE])
def update_invoice(invoice_id: int, data: InvoiceUpdate, db: Session = Depends(get_db)):
    return invoices.update(db, invoice_id, data)


@router.delete(
    "/invoices/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[MANAGE]
)
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)):
    """Supprime un BROUILLON (ses bons de livraison redeviennent à facturer)."""
    invoices.delete(db, invoice_id)


@router.post("/invoices/{invoice_id}/lines", response_model=InvoiceRead, dependencies=[MANAGE])
def add_line(invoice_id: int, data: LineIn, db: Session = Depends(get_db)):
    return invoices.add_line(db, invoice_id, data)


@router.put(
    "/invoices/{invoice_id}/lines/{line_id}", response_model=InvoiceRead, dependencies=[MANAGE]
)
def update_line(invoice_id: int, line_id: int, data: LineIn, db: Session = Depends(get_db)):
    return invoices.update_line(db, invoice_id, line_id, data)


@router.delete(
    "/invoices/{invoice_id}/lines/{line_id}", response_model=InvoiceRead, dependencies=[MANAGE]
)
def delete_line(invoice_id: int, line_id: int, db: Session = Depends(get_db)):
    return invoices.delete_line(db, invoice_id, line_id)


@router.post("/invoices/{invoice_id}/issue", response_model=InvoiceRead, dependencies=[MANAGE])
def issue(invoice_id: int, db: Session = Depends(get_db), ctx: RequestContext = MANAGE):
    """Émet : numéro définitif, échéance, et la facture devient inaltérable."""
    return invoices.issue(db, ctx, invoice_id)


@router.post(
    "/invoices/{invoice_id}/credit-note", response_model=InvoiceRead, dependencies=[MANAGE]
)
def credit_note(invoice_id: int, data: CreditNoteIn, db: Session = Depends(get_db)):
    """Prépare un avoir (brouillon) sur tout ou partie d'une facture émise."""
    return invoices.credit_note(db, invoice_id, data)


@router.post(
    "/credit-notes/{credit_note_id}/apply", response_model=InvoiceRead, dependencies=[PAYMENTS]
)
def apply_credit_note(credit_note_id: int, data: CreditApply, db: Session = Depends(get_db)):
    """Impute le crédit d'un avoir sur une autre facture du client."""
    return invoices.apply_credit_note(db, credit_note_id, data.invoice_id, data.amount)


@router.get("/invoices/{invoice_id}/pdf", dependencies=[READ])
def invoice_pdf(invoice_id: int, db: Session = Depends(get_db)):
    """PDF de la facture : Factur-X (XML EN 16931 embarqué) dès qu'elle est émise."""
    invoice = invoices.get(db, invoice_id)
    name = invoice.number or f"brouillon-{invoice.id}"
    return _file(pdf.render_invoice(db, invoice), f"{name}.pdf", "application/pdf")


@router.get("/invoices/{invoice_id}/xml", dependencies=[READ])
def invoice_xml(invoice_id: int, db: Session = Depends(get_db)):
    invoice = invoices.get(db, invoice_id)
    if invoice.status != "emise":
        raise Invalid("Le XML Factur-X existe une fois la facture émise")
    return _file(pdf.invoice_xml(db, invoice), f"{invoice.number}.xml", "application/xml", False)


# --- Règlements, échéancier -------------------------------------------------------------


@router.get("/payments", response_model=PaymentPage, dependencies=[READ])
def list_payments(
    customer_id: int | None = None,
    unallocated: bool = False,
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return payments.list_payments(
        db, customer_id=customer_id, unallocated=unallocated, limit=limit, offset=offset
    )


@router.post("/payments", response_model=PaymentRead, status_code=201, dependencies=[PAYMENTS])
def create_payment(data: PaymentIn, db: Session = Depends(get_db)):
    """Encaissement. Sans affectation précisée : lettré sur les factures les plus anciennes."""
    return payments.create_payment(db, data)


@router.post("/payments/{payment_id}/allocate", response_model=PaymentRead, dependencies=[PAYMENTS])
def allocate(payment_id: int, data: Allocate, db: Session = Depends(get_db)):
    return payments.allocate_payment(db, payment_id, data)


@router.delete(
    "/payments/{payment_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[PAYMENTS]
)
def delete_payment(payment_id: int, db: Session = Depends(get_db)):
    payments.delete_payment(db, payment_id)


@router.delete(
    "/allocations/{allocation_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[PAYMENTS]
)
def unallocate(allocation_id: int, db: Session = Depends(get_db)):
    """Défait un lettrage (erreur d'affectation)."""
    payments.unallocate(db, allocation_id)


@router.get("/customers/{customer_id}/account", response_model=CustomerAccount, dependencies=[READ])
def customer_account(customer_id: int, db: Session = Depends(get_db)):
    return payments.customer_account(db, customer_id)


@router.get("/receivables", response_model=Receivables, dependencies=[READ])
def receivables(db: Session = Depends(get_db)):
    """Balance âgée des créances clients."""
    return payments.receivables(db)


@router.post("/customers/{customer_id}/reminder", dependencies=[PAYMENTS])
def reminder(customer_id: int, db: Session = Depends(get_db)):
    """Relance : note la relance sur les factures en retard et renvoie la lettre (PDF)."""
    overdue = payments.mark_reminded(db, customer_id)
    return _file(pdf.render_reminder(db, customer_id, overdue), "relance.pdf", "application/pdf")


# --- Factures fournisseur ---------------------------------------------------------------


@router.get("/supplier-invoices", response_model=SupplierInvoicePage, dependencies=[READ])
def list_supplier_invoices(
    status: Literal["brouillon", "bon_a_payer", "annulee"] | None = None,
    unpaid: bool = False,
    partner_id: int | None = None,
    q: str | None = Query(None, max_length=100),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return suppliers.list_invoices(
        db, status=status, unpaid=unpaid, partner_id=partner_id, q=q, limit=limit, offset=offset
    )


@router.get(
    "/suppliers/{partner_id}/to-invoice", response_model=list[ReceptionToBill], dependencies=[READ]
)
def receptions_to_bill(partner_id: int, db: Session = Depends(get_db)):
    """Réceptions de ce fournisseur pas encore rapprochées d'une facture."""
    return suppliers.receptions_to_bill(db, partner_id)


@router.post(
    "/supplier-invoices",
    response_model=SupplierInvoiceRead,
    status_code=201,
    dependencies=[SUPPLIERS],
)
def create_supplier_invoice(data: SupplierInvoiceCreate, db: Session = Depends(get_db)):
    return suppliers.create(db, data)


@router.get(
    "/supplier-invoices/{invoice_id}", response_model=SupplierInvoiceRead, dependencies=[READ]
)
def get_supplier_invoice(invoice_id: int, db: Session = Depends(get_db)):
    return suppliers.get_invoice(db, invoice_id)


@router.patch(
    "/supplier-invoices/{invoice_id}", response_model=SupplierInvoiceRead, dependencies=[SUPPLIERS]
)
def update_supplier_invoice(
    invoice_id: int, data: SupplierInvoiceUpdate, db: Session = Depends(get_db)
):
    return suppliers.update(db, invoice_id, data)


@router.post(
    "/supplier-invoices/{invoice_id}/lines",
    response_model=SupplierInvoiceRead,
    dependencies=[SUPPLIERS],
)
def add_supplier_line(invoice_id: int, data: SupplierLineIn, db: Session = Depends(get_db)):
    return suppliers.add_line(db, invoice_id, data)


@router.put(
    "/supplier-invoices/{invoice_id}/lines/{line_id}",
    response_model=SupplierInvoiceRead,
    dependencies=[SUPPLIERS],
)
def update_supplier_line(
    invoice_id: int, line_id: int, data: SupplierLineIn, db: Session = Depends(get_db)
):
    return suppliers.update_line(db, invoice_id, line_id, data)


@router.delete(
    "/supplier-invoices/{invoice_id}/lines/{line_id}",
    response_model=SupplierInvoiceRead,
    dependencies=[SUPPLIERS],
)
def delete_supplier_line(invoice_id: int, line_id: int, db: Session = Depends(get_db)):
    return suppliers.delete_line(db, invoice_id, line_id)


@router.post("/supplier-invoices/{invoice_id}/approve", response_model=SupplierInvoiceRead)
def approve_supplier_invoice(
    invoice_id: int, data: Approve, db: Session = Depends(get_db), ctx: RequestContext = SUPPLIERS
):
    """Bon à payer. Avec des écarts, une justification est obligatoire."""
    return suppliers.approve(db, ctx, invoice_id, data)


@router.post(
    "/supplier-invoices/{invoice_id}/cancel",
    response_model=SupplierInvoiceRead,
    dependencies=[SUPPLIERS],
)
def cancel_supplier_invoice(invoice_id: int, db: Session = Depends(get_db)):
    return suppliers.cancel(db, invoice_id)


@router.post(
    "/supplier-invoices/{invoice_id}/payments",
    response_model=SupplierInvoiceRead,
    dependencies=[SUPPLIERS],
)
def pay_supplier_invoice(invoice_id: int, data: SupplierPaymentIn, db: Session = Depends(get_db)):
    return suppliers.pay(db, invoice_id, data)


# --- Comptabilité -----------------------------------------------------------------------


def _period(start: date, end: date) -> None:
    if end < start:
        raise Invalid("La date de fin précède la date de début")
    if (end - start).days > 366:
        raise Invalid("Période limitée à un an")


@router.get("/accounting/entries", response_model=EntriesPage, dependencies=[ACCOUNTING])
def entries(start: date, end: date, db: Session = Depends(get_db)):
    _period(start, end)
    return accounting.entries(db, start, end)


@router.get("/accounting/export.csv", dependencies=[ACCOUNTING])
def export_csv(start: date, end: date, db: Session = Depends(get_db)):
    _period(start, end)
    content = accounting.to_csv(accounting.entries(db, start, end))
    return _file(content, f"ecritures-{start}-{end}.csv", "text/csv; charset=utf-8", False)


@router.get("/accounting/fec", dependencies=[ACCOUNTING])
def export_fec(
    start: date, end: date, db: Session = Depends(get_db), ctx: RequestContext = ACCOUNTING
):
    """Fichier des Écritures Comptables (format de l'administration fiscale)."""
    _period(start, end)
    content = accounting.to_fec(db, accounting.entries(db, start, end))
    name = accounting.fec_filename(db, ctx.company_id, end)
    return _file(content, name, "text/plain; charset=utf-8", False)
