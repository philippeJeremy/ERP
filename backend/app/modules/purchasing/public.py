"""Interface publique du module achats : ce que les autres modules lisent.

La facturation fournisseur lit les réceptions (quantités reçues, prix net commandé)
pour contrôler les factures reçues.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.purchasing.models import PurchaseOrder, PurchaseOrderLine, Reception
from app.modules.purchasing.service import get_order


@dataclass
class ReceivedLine:
    reception_line_id: int
    order_line_id: int
    article_id: int | None
    supplier_ref: str | None
    designation: str
    quantity: Decimal  # reçu
    net_price: Decimal  # prix net unitaire commandé (remise déduite)


@dataclass
class ReceptionToInvoice:
    id: int
    number: str
    received_on: date
    delivery_note: str | None
    order_id: int
    order_number: str
    partner_id: int
    lines: list[ReceivedLine] = field(default_factory=list)


def _load(db: Session, query) -> list[ReceptionToInvoice]:
    rows = db.execute(
        query.join(PurchaseOrder, PurchaseOrder.id == Reception.order_id)
        .add_columns(PurchaseOrder)
        .order_by(Reception.received_on, Reception.id)
    ).all()
    ids = {x.order_line_id for r, _ in rows for x in r.lines}
    order_lines = (
        {
            x.id: x
            for x in db.scalars(select(PurchaseOrderLine).where(PurchaseOrderLine.id.in_(ids)))
        }
        if ids
        else {}
    )
    result = []
    for reception, order in rows:
        item = ReceptionToInvoice(
            id=reception.id, number=reception.number, received_on=reception.received_on,
            delivery_note=reception.delivery_note, order_id=order.id,
            order_number=order.number or "", partner_id=order.partner_id,
        )  # fmt: skip
        for x in reception.lines:
            o = order_lines[x.order_line_id]
            net = (
                (o.line_total / o.quantity).quantize(Decimal("0.0001"))
                if o.quantity
                else o.unit_price
            )
            item.lines.append(
                ReceivedLine(
                    reception_line_id=x.id,
                    order_line_id=o.id,
                    article_id=o.article_id,
                    supplier_ref=o.supplier_ref,
                    designation=o.designation,
                    quantity=x.quantity,
                    net_price=net,
                )  # fmt: skip
            )
        result.append(item)
    return result


def receptions_for_supplier(db: Session, partner_id: int) -> list[ReceptionToInvoice]:
    return _load(db, select(Reception).where(PurchaseOrder.partner_id == partner_id))


def receptions_by_ids(db: Session, ids: set[int]) -> list[ReceptionToInvoice]:
    if not ids:
        return []
    return _load(db, select(Reception).where(Reception.id.in_(ids)))


__all__ = [
    "ReceivedLine",
    "ReceptionToInvoice",
    "get_order",
    "receptions_by_ids",
    "receptions_for_supplier",
]
