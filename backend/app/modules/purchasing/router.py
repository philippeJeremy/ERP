"""Routes HTTP du module purchasing."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.db import get_db
from app.modules.auth.public import require
from app.modules.purchasing import pdf, service
from app.modules.purchasing.schemas import (
    Acknowledge,
    LineIn,
    OrderCreate,
    OrderPage,
    OrderRead,
    OrderUpdate,
    Reason,
    Receive,
    SettingsIn,
    SettingsRead,
)
from app.shared.schemas import Schema

router = APIRouter(prefix="/purchasing", tags=["Achats"])

READ = Depends(require("purchasing:read"))
MANAGE = Depends(require("purchasing:manage"))
APPROVE = Depends(require("purchasing:approve"))


class Version(Schema):
    version: int


@router.get("/orders", response_model=OrderPage, dependencies=[READ])
def list_orders(
    group: Literal["a_traiter", "en_cours", "terminees"] | None = None,
    status: str | None = Query(None, max_length=20),
    partner_id: int | None = None,
    q: str | None = Query(
        None, max_length=100, description="N° de commande, n° fournisseur ou fournisseur"
    ),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return service.list_orders(
        db, group=group, status=status, partner_id=partner_id, q=q, limit=limit, offset=offset
    )


@router.post(
    "/orders", response_model=OrderRead, status_code=status.HTTP_201_CREATED, dependencies=[MANAGE]
)
def create_order(data: OrderCreate, db: Session = Depends(get_db)):
    return service.create_order(db, data)


@router.get("/orders/{order_id}", response_model=OrderRead, dependencies=[READ])
def get_order(order_id: int, db: Session = Depends(get_db)):
    return service.get_order(db, order_id)


@router.patch("/orders/{order_id}", response_model=OrderRead, dependencies=[MANAGE])
def update_order(order_id: int, data: OrderUpdate, db: Session = Depends(get_db)):
    return service.update_order(db, order_id, data)


@router.delete("/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[MANAGE])
def delete_order(order_id: int, db: Session = Depends(get_db)):
    """Supprime un brouillon (une commande validée s'annule)."""
    service.delete_order(db, order_id)


@router.post("/orders/{order_id}/lines", response_model=OrderRead, dependencies=[MANAGE])
def add_line(order_id: int, data: LineIn, db: Session = Depends(get_db)):
    return service.add_line(db, order_id, data)


@router.put("/orders/{order_id}/lines/{line_id}", response_model=OrderRead, dependencies=[MANAGE])
def update_line(order_id: int, line_id: int, data: LineIn, db: Session = Depends(get_db)):
    return service.update_line(db, order_id, line_id, data)


@router.delete(
    "/orders/{order_id}/lines/{line_id}", response_model=OrderRead, dependencies=[MANAGE]
)
def delete_line(order_id: int, line_id: int, db: Session = Depends(get_db)):
    return service.delete_line(db, order_id, line_id)


@router.post("/orders/{order_id}/submit", response_model=OrderRead)
def submit(
    order_id: int, data: Version, db: Session = Depends(get_db), ctx: RequestContext = MANAGE
):
    """Valider : la commande est numérotée, ou part en validation si elle dépasse le seuil."""
    return service.submit(db, ctx, order_id, data.version)


@router.post("/orders/{order_id}/approve", response_model=OrderRead)
def approve(
    order_id: int, data: Version, db: Session = Depends(get_db), ctx: RequestContext = APPROVE
):
    return service.approve(db, ctx, order_id, data.version)


@router.post("/orders/{order_id}/reject", response_model=OrderRead, dependencies=[APPROVE])
def reject(order_id: int, data: Reason, db: Session = Depends(get_db)):
    return service.reject(db, order_id, data.reason)


@router.post("/orders/{order_id}/send", response_model=OrderRead, dependencies=[MANAGE])
def mark_sent(order_id: int, db: Session = Depends(get_db)):
    return service.mark_sent(db, order_id)


@router.post("/orders/{order_id}/acknowledge", response_model=OrderRead, dependencies=[MANAGE])
def acknowledge(order_id: int, data: Acknowledge, db: Session = Depends(get_db)):
    return service.acknowledge(db, order_id, data)


@router.post("/orders/{order_id}/receive", response_model=OrderRead, dependencies=[MANAGE])
def receive(order_id: int, data: Receive, db: Session = Depends(get_db)):
    return service.receive(db, order_id, data)


@router.post("/orders/{order_id}/close", response_model=OrderRead, dependencies=[MANAGE])
def close(order_id: int, data: Reason, db: Session = Depends(get_db)):
    return service.close(db, order_id, data.reason)


@router.post("/orders/{order_id}/cancel", response_model=OrderRead, dependencies=[MANAGE])
def cancel(order_id: int, data: Reason, db: Session = Depends(get_db)):
    return service.cancel(db, order_id, data.reason)


@router.get("/orders/{order_id}/pdf", dependencies=[READ])
def order_pdf(order_id: int, db: Session = Depends(get_db)):
    """Le bon de commande en PDF (à partir de la validation)."""
    order = service._get(db, order_id)
    if order.number is None:
        raise service.Invalid("Le bon de commande est disponible une fois la commande validée")
    return Response(
        pdf.render(db, order),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{order.number}.pdf"'},
    )


@router.get("/settings", response_model=SettingsRead, dependencies=[READ])
def get_settings(db: Session = Depends(get_db)):
    return service.get_settings(db)


@router.put("/settings", response_model=SettingsRead, dependencies=[APPROVE])
def save_settings(data: SettingsIn, db: Session = Depends(get_db)):
    return service.save_settings(db, data)
