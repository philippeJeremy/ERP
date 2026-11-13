"""Accès aux données du module purchasing (filtré par la RLS sur la société courante)."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.purchasing.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseSettings,
    Reception,
)

STATUS_GROUPS = {
    "a_traiter": ("brouillon", "a_valider", "validee"),
    "en_cours": ("envoyee", "confirmee", "partielle"),
    "terminees": ("recue", "cloturee", "annulee"),
}


def get_order(db: Session, order_id: int, *, for_update: bool = False) -> PurchaseOrder | None:
    query = select(PurchaseOrder).where(PurchaseOrder.id == order_id)
    if for_update:
        query = query.with_for_update()
    return db.scalar(query)


def receptions_of(db: Session, order_id: int) -> list[Reception]:
    return list(
        db.scalars(select(Reception).where(Reception.order_id == order_id).order_by(Reception.id))
    )


def get_settings(db: Session) -> PurchaseSettings | None:
    return db.scalar(select(PurchaseSettings))


def search_orders(
    db: Session,
    *,
    group: str | None,
    status: str | None,
    partner_id: int | None,
    q: str | None,
    q_partner_ids: list[int],
    limit: int,
    offset: int,
) -> tuple[list[tuple], int]:
    query = select(PurchaseOrder)
    if status:
        query = query.where(PurchaseOrder.status == status)
    elif group in STATUS_GROUPS:
        query = query.where(PurchaseOrder.status.in_(STATUS_GROUPS[group]))
    if partner_id:
        query = query.where(PurchaseOrder.partner_id == partner_id)
    if q:
        # N° de commande, n° chez le fournisseur, ou nom du fournisseur (ids fournis
        # par le module partners : on ne lit pas ses tables).
        query = query.where(
            or_(
                PurchaseOrder.number.ilike(f"%{q}%"),
                PurchaseOrder.supplier_reference.ilike(f"%{q}%"),
                PurchaseOrder.partner_id.in_(q_partner_ids or [0]),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    progress = (
        select(
            PurchaseOrderLine.order_id,
            func.count().label("line_count"),
            func.sum(PurchaseOrderLine.quantity).label("qty"),
            func.sum(func.least(PurchaseOrderLine.received_qty, PurchaseOrderLine.quantity)).label(
                "received"
            ),
        )
        .group_by(PurchaseOrderLine.order_id)
        .subquery()
    )
    rows = db.execute(
        query.add_columns(progress.c.line_count, progress.c.qty, progress.c.received)
        .outerjoin(progress, progress.c.order_id == PurchaseOrder.id)
        .order_by(PurchaseOrder.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [tuple(r) for r in rows], total
