"""Envoi des devis par mail."""

from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.modules.mailing import public as mailing
from app.modules.partners import public as partners
from app.modules.sales import pdf, service
from app.modules.sales.schemas import QuoteRead


def _values(quote) -> dict[str, str]:
    return {
        "numero": quote.number,
        "date": mailing.fdate(quote.quote_date),
        "validite": mailing.fdate(quote.valid_until),
        "montant_ttc": mailing.euros(quote.total_ttc),
        "reference": quote.customer_reference or "",
    }


def quote_draft(db: Session, ctx: RequestContext, quote_id: int) -> mailing.EmailDraft:
    quote = service._quote(db, quote_id)
    terms = partners.customer_terms(db, quote.customer_id)
    to, known = partners.email_suggestions(db, quote.customer_id, "devis")
    return mailing.draft(
        db, ctx, kind="devis", values={**_values(quote), "destinataire": terms.name}, to=to,
        suggestions=known, attachments=[f"Devis {quote.number}.pdf"], document_type="quote",
        document_id=quote.id,
    )  # fmt: skip


def send_quote(
    db: Session, ctx: RequestContext, quote_id: int, data: mailing.EmailSend
) -> QuoteRead:
    """Envoie le devis (PDF joint) ; un brouillon passe en « envoyé »."""
    quote = service._quote(db, quote_id, for_update=True)
    if quote.status == "annule":
        raise service._status_error(quote, "envoyer")
    if not quote.lines:
        raise service.Invalid("Le devis n'a aucune ligne")
    if quote.status == "brouillon":
        quote.status = "envoye"
        quote.sent_at = service.now()
    content = pdf.render_quote(db, quote)
    mailing.queue(
        db, ctx, kind="devis", data=data,
        attachments=[(f"Devis {quote.number}.pdf", "application/pdf", content)],
        document_type="quote", document_id=quote.id, document_number=quote.number,
        partner_id=quote.customer_id,
    )  # fmt: skip
    return service.quote_read(db, quote)
