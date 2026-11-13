"""Interface publique du module ventes : ce que la facturation lit.

- `deliveries_for_customer` / `deliveries_by_ids` : les bons de livraison et leurs
  lignes, au prix de la commande (c'est ce qu'on facture) ;
- `register_outstanding_source` : la facturation y branche le calcul de ce que le
  client doit (factures impayées, livraisons non facturées) pour l'encours.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.modules.sales.models import Delivery, SalesOrder, SalesOrderLine
from app.modules.sales.service import OUTSTANDING_SOURCES


@dataclass
class DeliveredLine:
    order_line_id: int
    article_id: int | None
    designation: str
    quantity: Decimal
    unit_price: Decimal
    discount_pct: Decimal
    eco_fee: Decimal
    vat_rate: Decimal


@dataclass
class DeliveryToInvoice:
    id: int
    number: str
    delivered_on: date
    order_id: int
    order_number: str
    order_status: str
    customer_id: int
    customer_reference: str | None
    lines: list[DeliveredLine] = field(default_factory=list)


def _load(db: Session, query) -> list[DeliveryToInvoice]:
    rows = db.execute(
        query.join(SalesOrder, SalesOrder.id == Delivery.order_id)
        .add_columns(SalesOrder)
        .order_by(Delivery.delivered_on, Delivery.id)
    ).all()
    line_ids = {x.order_line_id for d, _ in rows for x in d.lines}
    order_lines = (
        {x.id: x for x in db.scalars(select(SalesOrderLine).where(SalesOrderLine.id.in_(line_ids)))}
        if line_ids
        else {}
    )
    result = []
    for delivery, order in rows:
        item = DeliveryToInvoice(
            id=delivery.id, number=delivery.number, delivered_on=delivery.delivered_on,
            order_id=order.id, order_number=order.number, order_status=order.status,
            customer_id=order.customer_id, customer_reference=order.customer_reference,
        )  # fmt: skip
        quantities: dict[int, Decimal] = {}
        for x in delivery.lines:  # un article peut sortir en plusieurs lots (DOT)
            quantities[x.order_line_id] = quantities.get(x.order_line_id, Decimal(0)) + x.quantity
        for line_id, quantity in quantities.items():
            o = order_lines[line_id]
            item.lines.append(
                DeliveredLine(
                    order_line_id=o.id,
                    article_id=o.article_id,
                    designation=o.designation,
                    quantity=quantity,
                    unit_price=o.unit_price,
                    discount_pct=o.discount_pct,
                    eco_fee=o.eco_fee,
                    vat_rate=o.vat_rate,
                )  # fmt: skip
            )
        item.lines.sort(key=lambda x: order_lines[x.order_line_id].line_no)
        result.append(item)
    return result


def deliveries_for_customer(db: Session, customer_id: int) -> list[DeliveryToInvoice]:
    return _load(db, select(Delivery).where(SalesOrder.customer_id == customer_id))


def deliveries_by_ids(db: Session, ids: set[int]) -> list[DeliveryToInvoice]:
    if not ids:
        return []
    return _load(db, select(Delivery).where(Delivery.id.in_(ids)))


def uninvoiced_deliveries(
    db: Session, invoiced_ids: Select, customer_id: int | None = None
) -> list[DeliveryToInvoice]:
    """Les BL pas encore facturés (`invoiced_ids` : sous-requête des id déjà facturés)."""
    query = select(Delivery).where(Delivery.id.not_in(invoiced_ids))
    if customer_id is not None:
        query = query.where(SalesOrder.customer_id == customer_id)
    return _load(db, query)


def register_outstanding_source(source: Callable[[Session, int], Decimal]) -> None:
    """Ajoute un calcul d'encours (TTC dû par un client) à celui des commandes en cours."""
    if source not in OUTSTANDING_SOURCES:
        OUTSTANDING_SOURCES.append(source)


__all__ = [
    "DeliveredLine",
    "DeliveryToInvoice",
    "deliveries_by_ids",
    "deliveries_for_customer",
    "register_outstanding_source",
    "uninvoiced_deliveries",
]
