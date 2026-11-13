"""Accès aux tables `sales.*` (la RLS limite tout à la société courante)."""

from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.sales.models import (
    Delivery,
    Price,
    Quote,
    SalesOrder,
    SalesSettings,
)


def get_settings(db: Session) -> SalesSettings | None:
    return db.scalar(select(SalesSettings))


# --- Tarif ------------------------------------------------------------------------------


def get_price(db: Session, article_id: int) -> Price | None:
    return db.scalar(select(Price).where(Price.article_id == article_id))


def prices_of(db: Session, article_ids: list[int]) -> dict[int, Price]:
    if not article_ids:
        return {}
    return {
        p.article_id: p for p in db.scalars(select(Price).where(Price.article_id.in_(article_ids)))
    }


def priced_article_ids() -> Select:
    return select(Price.article_id)


# --- Devis ------------------------------------------------------------------------------


def get_quote(db: Session, quote_id: int, *, for_update: bool = False) -> Quote | None:
    query = select(Quote).where(Quote.id == quote_id)
    if for_update:
        query = query.with_for_update(of=Quote)
    return db.scalar(query)


def list_quotes(
    db: Session,
    *,
    status: str | None,
    customer_id: int | None,
    customer_ids: list[int] | None,
    q: str | None,
    limit: int,
    offset: int,
) -> tuple[list[Quote], int]:
    query = select(Quote)
    if status:
        query = query.where(Quote.status == status)
    if customer_id is not None:
        query = query.where(Quote.customer_id == customer_id)
    if q:
        condition = Quote.number.ilike(f"%{q}%") | Quote.customer_reference.ilike(f"%{q}%")
        if customer_ids:
            condition = condition | Quote.customer_id.in_(customer_ids)
        query = query.where(condition)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(Quote.id.desc()).limit(limit).offset(offset))
    return list(rows), total


# --- Commandes --------------------------------------------------------------------------


def get_order(db: Session, order_id: int, *, for_update: bool = False) -> SalesOrder | None:
    query = select(SalesOrder).where(SalesOrder.id == order_id)
    if for_update:
        query = query.with_for_update(of=SalesOrder)
    return db.scalar(query)


def order_numbers(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return dict(
        db.execute(select(SalesOrder.id, SalesOrder.number).where(SalesOrder.id.in_(ids))).all()
    )


def quote_number(db: Session, quote_id: int) -> str | None:
    return db.scalar(select(Quote.number).where(Quote.id == quote_id))


def list_orders(
    db: Session,
    *,
    status: str | None,
    open_only: bool,
    customer_id: int | None,
    customer_ids: list[int] | None,
    q: str | None,
    limit: int,
    offset: int,
) -> tuple[list[SalesOrder], int]:
    query = select(SalesOrder)
    if status:
        query = query.where(SalesOrder.status == status)
    if open_only:
        query = query.where(SalesOrder.status.in_(("brouillon", "confirmee", "partielle")))
    if customer_id is not None:
        query = query.where(SalesOrder.customer_id == customer_id)
    if q:
        condition = SalesOrder.number.ilike(f"%{q}%") | SalesOrder.customer_reference.ilike(
            f"%{q}%"
        )
        if customer_ids:
            condition = condition | SalesOrder.customer_id.in_(customer_ids)
        query = query.where(condition)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(SalesOrder.id.desc()).limit(limit).offset(offset))
    return list(rows), total


def outstanding(db: Session, customer_id: int, exclude_order_id: int | None = None) -> Decimal:
    """Encours des commandes : le RESTE À LIVRER (TTC) des commandes confirmées.
    Ce qui est livré est compté par la facturation (non facturé, puis facture impayée)."""
    query = select(SalesOrder).where(
        SalesOrder.customer_id == customer_id,
        SalesOrder.status.in_(("confirmee", "partielle")),
    )
    if exclude_order_id is not None:
        query = query.where(SalesOrder.id != exclude_order_id)
    total = Decimal(0)
    for order in db.scalars(query):
        for line in order.lines:
            remaining = line.quantity - line.delivered_qty
            if remaining <= 0:
                continue
            ht = (line.line_total + line.quantity * line.eco_fee) * remaining / line.quantity
            total += ht * (1 + line.vat_rate / 100)
    return total.quantize(Decimal("0.01"))


def deliveries_of(db: Session, order_id: int) -> list[Delivery]:
    return list(
        db.scalars(select(Delivery).where(Delivery.order_id == order_id).order_by(Delivery.id))
    )


def get_delivery(db: Session, delivery_id: int) -> Delivery | None:
    return db.get(Delivery, delivery_id)
