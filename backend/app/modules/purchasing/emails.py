"""Envoi des bons de commande fournisseur par mail."""

from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.modules.mailing import public as mailing
from app.modules.org import public as org
from app.modules.partners import public as partners
from app.modules.purchasing import pdf, service
from app.modules.purchasing.schemas import OrderRead

SENDABLE = ("validee", "envoyee", "confirmee", "partielle")


def _order(db: Session, order_id: int, *, for_update: bool = False):
    order = service._get(db, order_id, for_update=for_update)
    if order.status not in SENDABLE:
        raise service.Invalid("Le bon de commande s'envoie une fois la commande validée")
    return order


def order_draft(db: Session, ctx: RequestContext, order_id: int) -> mailing.EmailDraft:
    order = _order(db, order_id)
    site = org.get_site(db, order.site_id)
    name = partners.partner_names(db, {order.partner_id})[order.partner_id][1]
    to, known = partners.email_suggestions(db, order.partner_id, "commande")
    values = {
        "numero": order.number, "date": mailing.fdate(order.order_date), "depot": site.name,
        "livraison": f", pour le {mailing.fdate(order.expected_date)}" if order.expected_date else "",  # noqa: E501
        "destinataire": name,
    }  # fmt: skip
    return mailing.draft(
        db, ctx, kind="commande_fournisseur", values=values, to=to, suggestions=known,
        attachments=[f"Commande {order.number}.pdf"], document_type="purchase_order",
        document_id=order.id,
    )  # fmt: skip


def send_order(
    db: Session, ctx: RequestContext, order_id: int, data: mailing.EmailSend
) -> OrderRead:
    """Envoie le bon de commande ; une commande validée passe en « envoyée »."""
    order = _order(db, order_id, for_update=True)
    if order.status == "validee":
        order.status = "envoyee"
        order.sent_at = service.now()
    content = pdf.render(db, order)
    mailing.queue(
        db, ctx, kind="commande_fournisseur", data=data,
        attachments=[(f"Commande {order.number}.pdf", "application/pdf", content)],
        document_type="purchase_order", document_id=order.id, document_number=order.number,
        partner_id=order.partner_id,
    )  # fmt: skip
    return service.order_read(db, order)
