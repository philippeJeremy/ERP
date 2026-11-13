"""Routes HTTP du module ventes."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import NotFound
from app.modules.auth.public import require
from app.modules.sales import pdf, service
from app.modules.sales.schemas import (
    Accept,
    Confirm,
    CustomerActivity,
    Deliver,
    LineIn,
    OrderCreate,
    OrderPage,
    OrderRead,
    OrderStatus,
    OrderUpdate,
    PriceIn,
    PricePage,
    PriceRow,
    Pricing,
    QuoteCreate,
    QuotePage,
    QuoteRead,
    QuoteStatus,
    QuoteUpdate,
    Reason,
    SettingsIn,
    SettingsRead,
)

router = APIRouter(prefix="/sales", tags=["Ventes"])

READ = Depends(require("sales:read"))
MANAGE = Depends(require("sales:manage"))
DELIVER = Depends(require("sales:deliver"))
PRICES = Depends(require("sales:prices"))


def _pdf(content: bytes, name: str) -> Response:
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{name}.pdf"'},
    )


# --- Réglages, tarif ---------------------------------------------------------------------


@router.get("/settings", response_model=SettingsRead, dependencies=[READ])
def get_settings(db: Session = Depends(get_db)):
    return service.get_settings(db)


@router.put("/settings", response_model=SettingsRead, dependencies=[PRICES])
def save_settings(data: SettingsIn, db: Session = Depends(get_db)):
    return service.save_settings(db, data)


@router.get("/prices", response_model=PricePage, dependencies=[READ])
def list_prices(
    q: str | None = Query(None, max_length=100),
    kind: Literal["pneu", "piece", "accessoire"] | None = None,
    missing: bool = False,
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return service.list_prices(db, q=q, kind=kind, missing=missing, limit=limit, offset=offset)


@router.put("/prices/{article_id}", response_model=PriceRow, dependencies=[PRICES])
def save_price(article_id: int, data: PriceIn, db: Session = Depends(get_db)):
    return service.save_price(db, article_id, data)


@router.delete(
    "/prices/{article_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[PRICES]
)
def delete_price(article_id: int, db: Session = Depends(get_db)):
    service.delete_price(db, article_id)


@router.get("/pricing", response_model=Pricing, dependencies=[READ])
def pricing(
    customer_id: int, article_id: int, site_id: int | None = None, db: Session = Depends(get_db)
):
    """Prix proposé à un client pour un article, et le stock disponible du dépôt."""
    return service.pricing(db, customer_id, article_id, site_id)


@router.get(
    "/customers/{customer_id}/activity", response_model=CustomerActivity, dependencies=[READ]
)
def customer_activity(customer_id: int, db: Session = Depends(get_db)):
    return service.customer_activity(db, customer_id)


# --- Devis -------------------------------------------------------------------------------


@router.get("/quotes", response_model=QuotePage, dependencies=[READ])
def list_quotes(
    status: QuoteStatus | None = None,
    customer_id: int | None = None,
    q: str | None = Query(None, max_length=100),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return service.list_quotes(
        db, status=status, customer_id=customer_id, q=q, limit=limit, offset=offset
    )


@router.post("/quotes", response_model=QuoteRead, status_code=201, dependencies=[MANAGE])
def create_quote(data: QuoteCreate, db: Session = Depends(get_db)):
    return service.create_quote(db, data)


@router.get("/quotes/{quote_id}", response_model=QuoteRead, dependencies=[READ])
def get_quote(quote_id: int, db: Session = Depends(get_db)):
    return service.get_quote(db, quote_id)


@router.patch("/quotes/{quote_id}", response_model=QuoteRead, dependencies=[MANAGE])
def update_quote(quote_id: int, data: QuoteUpdate, db: Session = Depends(get_db)):
    return service.update_quote(db, quote_id, data)


@router.post("/quotes/{quote_id}/lines", response_model=QuoteRead, dependencies=[MANAGE])
def add_quote_line(quote_id: int, data: LineIn, db: Session = Depends(get_db)):
    return service.add_quote_line(db, quote_id, data)


@router.put("/quotes/{quote_id}/lines/{line_id}", response_model=QuoteRead, dependencies=[MANAGE])
def update_quote_line(quote_id: int, line_id: int, data: LineIn, db: Session = Depends(get_db)):
    return service.update_quote_line(db, quote_id, line_id, data)


@router.delete(
    "/quotes/{quote_id}/lines/{line_id}", response_model=QuoteRead, dependencies=[MANAGE]
)
def delete_quote_line(quote_id: int, line_id: int, db: Session = Depends(get_db)):
    return service.delete_quote_line(db, quote_id, line_id)


@router.post("/quotes/{quote_id}/send", response_model=QuoteRead, dependencies=[MANAGE])
def send_quote(quote_id: int, db: Session = Depends(get_db)):
    return service.send_quote(db, quote_id)


@router.post("/quotes/{quote_id}/reopen", response_model=QuoteRead, dependencies=[MANAGE])
def reopen_quote(quote_id: int, db: Session = Depends(get_db)):
    return service.reopen_quote(db, quote_id)


@router.post("/quotes/{quote_id}/refuse", response_model=QuoteRead, dependencies=[MANAGE])
def refuse_quote(quote_id: int, data: Reason, db: Session = Depends(get_db)):
    return service.refuse_quote(db, quote_id, data.reason)


@router.post("/quotes/{quote_id}/cancel", response_model=QuoteRead, dependencies=[MANAGE])
def cancel_quote(quote_id: int, db: Session = Depends(get_db)):
    return service.cancel_quote(db, quote_id)


@router.post("/quotes/{quote_id}/accept", response_model=OrderRead, dependencies=[MANAGE])
def accept_quote(quote_id: int, data: Accept, db: Session = Depends(get_db)):
    """Accord du client : crée la commande confirmée et réserve le stock."""
    return service.accept_quote(db, quote_id, data)


@router.get("/quotes/{quote_id}/pdf", dependencies=[READ])
def quote_pdf(quote_id: int, db: Session = Depends(get_db)):
    quote = service._quote(db, quote_id)
    return _pdf(pdf.render_quote(db, quote), quote.number)


# --- Commandes ---------------------------------------------------------------------------


@router.get("/orders", response_model=OrderPage, dependencies=[READ])
def list_orders(
    status: OrderStatus | None = None,
    open: bool = Query(False, description="Brouillons, confirmées et partielles"),
    customer_id: int | None = None,
    q: str | None = Query(None, max_length=100),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return service.list_orders(
        db, status=status, open_only=open, customer_id=customer_id, q=q, limit=limit, offset=offset
    )


@router.post("/orders", response_model=OrderRead, status_code=201, dependencies=[MANAGE])
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
    service.delete_order(db, order_id)


@router.post("/orders/{order_id}/lines", response_model=OrderRead, dependencies=[MANAGE])
def add_order_line(order_id: int, data: LineIn, db: Session = Depends(get_db)):
    return service.add_order_line(db, order_id, data)


@router.put("/orders/{order_id}/lines/{line_id}", response_model=OrderRead, dependencies=[MANAGE])
def update_order_line(order_id: int, line_id: int, data: LineIn, db: Session = Depends(get_db)):
    return service.update_order_line(db, order_id, line_id, data)


@router.delete(
    "/orders/{order_id}/lines/{line_id}", response_model=OrderRead, dependencies=[MANAGE]
)
def delete_order_line(order_id: int, line_id: int, db: Session = Depends(get_db)):
    return service.delete_order_line(db, order_id, line_id)


@router.post("/orders/{order_id}/confirm", response_model=OrderRead, dependencies=[MANAGE])
def confirm_order(order_id: int, data: Confirm, db: Session = Depends(get_db)):
    """Confirme la commande et réserve le stock."""
    return service.confirm_order(db, order_id, data)


@router.post("/orders/{order_id}/reopen", response_model=OrderRead, dependencies=[MANAGE])
def reopen_order(order_id: int, db: Session = Depends(get_db)):
    return service.reopen_order(db, order_id)


@router.post("/orders/{order_id}/deliver", response_model=OrderRead, dependencies=[DELIVER])
def deliver(order_id: int, data: Deliver, db: Session = Depends(get_db)):
    """Livraison : sortie de stock (DOT les plus anciens d'abord) et bon de livraison."""
    return service.deliver(db, order_id, data)


@router.post("/orders/{order_id}/close", response_model=OrderRead, dependencies=[MANAGE])
def close_order(order_id: int, data: Reason, db: Session = Depends(get_db)):
    return service.close_order(db, order_id, data.reason)


@router.post("/orders/{order_id}/cancel", response_model=OrderRead, dependencies=[MANAGE])
def cancel_order(order_id: int, data: Reason, db: Session = Depends(get_db)):
    return service.cancel_order(db, order_id, data.reason)


@router.get("/deliveries/{delivery_id}/pdf", dependencies=[READ])
def delivery_pdf(delivery_id: int, db: Session = Depends(get_db)):
    from app.modules.sales import repository as repo

    delivery = repo.get_delivery(db, delivery_id)
    if delivery is None:
        raise NotFound("Bon de livraison introuvable")
    order = service._order(db, delivery.order_id)
    return _pdf(pdf.render_delivery(db, order, delivery), delivery.number)
