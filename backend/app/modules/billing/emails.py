"""Envoi des factures, avoirs et relances par mail."""

from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.errors import Conflict
from app.modules.billing import invoices as inv
from app.modules.billing import payments, pdf
from app.modules.billing.common import Invalid, now
from app.modules.billing.schemas import InvoiceRead
from app.modules.mailing import public as mailing
from app.modules.partners import public as partners

LEVELS = {1: "Rappel d'échéance", 2: "Deuxième relance"}


def _issued(db: Session, invoice_id: int, *, for_update: bool = False):
    invoice = inv.get(db, invoice_id, for_update=for_update)
    if invoice.status != "emise":
        raise Conflict("Émettez d'abord la facture avant de l'envoyer", code="statut_incompatible")
    return invoice


def _label(invoice) -> str:
    return f"{'Facture' if invoice.kind == 'facture' else 'Avoir'} {invoice.number}.pdf"


def invoice_draft(db: Session, ctx: RequestContext, invoice_id: int) -> mailing.EmailDraft:
    invoice = _issued(db, invoice_id)
    to, known = partners.email_suggestions(db, invoice.customer_id, "facture")
    values = {
        "numero": invoice.number, "date": mailing.fdate(invoice.issue_date),
        "echeance": mailing.fdate(invoice.due_date), "montant_ttc": mailing.euros(invoice.total_ttc),  # noqa: E501
        "destinataire": invoice.customer_name or "", "reference": invoice.customer_reference or "",
        "facture": inv.get(db, invoice.original_id).number if invoice.original_id else "",
    }  # fmt: skip
    return mailing.draft(
        db, ctx, kind=invoice.kind, values=values, to=to, suggestions=known,
        attachments=[_label(invoice)], document_type="invoice", document_id=invoice.id,
    )  # fmt: skip


def send_invoice(
    db: Session, ctx: RequestContext, invoice_id: int, data: mailing.EmailSend
) -> InvoiceRead:
    invoice = _issued(db, invoice_id, for_update=True)
    content = pdf.render_invoice(db, invoice)
    invoice.sent_at = now()
    mailing.queue(
        db, ctx, kind=invoice.kind, data=data,
        attachments=[(_label(invoice), "application/pdf", content)],
        document_type="invoice", document_id=invoice.id, document_number=invoice.number,
        partner_id=invoice.customer_id,
    )  # fmt: skip
    return inv.read(db, invoice)


def _reminder_values(db: Session, customer_id: int, invoices, level: int) -> dict[str, str]:
    lines = [
        f"- {x.number} du {mailing.fdate(x.issue_date)}, échue le {mailing.fdate(x.due_date)} : "
        f"{mailing.euros(inv.balance(x))}"
        for x in invoices
    ]
    total = sum((inv.balance(x) for x in invoices), invoices[0].total_ttc * 0)
    return {
        "destinataire": partners.customer_terms(db, customer_id).name,
        "factures": "\n".join(lines),
        "total_du": mailing.euros(total),
        "niveau": LEVELS.get(level, "Mise en demeure"),
    }


def reminder_draft(db: Session, ctx: RequestContext, customer_id: int) -> mailing.EmailDraft:
    overdue = payments.overdue_invoices(db, customer_id)
    if not overdue:
        raise Invalid("Ce client n'a aucune facture en retard")
    level = max(x.reminder_count for x in overdue) + 1
    to, known = partners.email_suggestions(db, customer_id, "facture")
    return mailing.draft(
        db, ctx, kind="relance", values=_reminder_values(db, customer_id, overdue, level),
        to=to, suggestions=known, attachments=["Relance.pdf"],
        document_type="customer", document_id=customer_id,
    )  # fmt: skip


def send_reminder(
    db: Session, ctx: RequestContext, customer_id: int, data: mailing.EmailSend
) -> dict:
    overdue = payments.overdue_invoices(db, customer_id)
    if not overdue:
        raise Invalid("Ce client n'a aucune facture en retard")
    stamp = now()
    for invoice in overdue:
        invoice.reminder_count += 1
        invoice.last_reminder_at = stamp
    db.flush()
    content = pdf.render_reminder(db, customer_id, overdue)
    mailing.queue(
        db, ctx, kind="relance", data=data,
        attachments=[("Relance.pdf", "application/pdf", content)],
        document_type="customer", document_id=customer_id, document_number=None,
        partner_id=customer_id,
    )  # fmt: skip
    return {"reminded": [x.number for x in overdue]}
