"""Routes HTTP du module inventory (le stock)."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.db import get_db
from app.modules.auth.public import require
from app.modules.inventory import service
from app.modules.inventory.models import COUNT_STATUSES, MOVE_KINDS
from app.modules.inventory.schemas import (
    AdjustIn,
    ArticleStock,
    CountCreate,
    CountEntries,
    CountLineAdd,
    CountPage,
    CountRead,
    CountValidate,
    LocationIn,
    LocationRead,
    MovePage,
    MoveRead,
    StockPage,
    TransferIn,
    TransferPage,
    TransferRead,
)

router = APIRouter(prefix="/inventory", tags=["Stock"])

READ = Depends(require("inventory:read"))
COUNT = Depends(require("inventory:count"))
MANAGE = Depends(require("inventory:manage"))

MoveKind = Literal[MOVE_KINDS]  # type: ignore[valid-type]
CountStatus = Literal[COUNT_STATUSES]  # type: ignore[valid-type]


# --- Emplacements ----------------------------------------------------------------------


@router.get("/sites/{site_id}/locations", response_model=list[LocationRead], dependencies=[READ])
def list_locations(site_id: int, active: bool | None = None, db: Session = Depends(get_db)):
    """Emplacements du dépôt (l'emplacement par défaut « QUAI » est créé au besoin)."""
    return service.list_locations(db, site_id, active)


@router.post(
    "/sites/{site_id}/locations",
    response_model=LocationRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[MANAGE],
)
def create_location(site_id: int, data: LocationIn, db: Session = Depends(get_db)):
    return service.save_location(db, data, site_id=site_id)


@router.put("/locations/{location_id}", response_model=LocationRead, dependencies=[MANAGE])
def update_location(location_id: int, data: LocationIn, db: Session = Depends(get_db)):
    return service.save_location(db, data, location_id=location_id)


@router.delete(
    "/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[MANAGE]
)
def delete_location(location_id: int, db: Session = Depends(get_db)):
    service.delete_location(db, location_id)


# --- État du stock et mouvements -------------------------------------------------------


@router.get("/stock", response_model=StockPage, dependencies=[READ])
def stock(
    site_id: int | None = None,
    location_id: int | None = None,
    q: str | None = Query(None, max_length=100, description="Code, EAN, désignation, dimension"),
    kind: Literal["pneu", "piece", "accessoire"] | None = None,
    sort: Literal["value", "quantity", "cost", "dot"] = "value",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return service.stock(
        db,
        site_id=site_id,
        location_id=location_id,
        q=q,
        kind=kind,
        sort=sort,
        descending=order == "desc",
        limit=limit,
        offset=offset,
    )


@router.get("/articles/{article_id}", response_model=ArticleStock, dependencies=[READ])
def article_stock(article_id: int, db: Session = Depends(get_db)):
    return service.article_stock(db, article_id)


@router.get("/moves", response_model=MovePage, dependencies=[READ])
def list_moves(
    article_id: int | None = None,
    site_id: int | None = None,
    kind: MoveKind | None = None,
    q: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return service.list_moves(
        db, article_id=article_id, site_id=site_id, kind=kind, q=q, limit=limit, offset=offset
    )


@router.post(
    "/adjustments",
    response_model=MoveRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[MANAGE],
)
def adjust(data: AdjustIn, db: Session = Depends(get_db)):
    """Ajustement manuel avec motif (casse, perte, vol, erreur…)."""
    return service.adjust(db, data)


# --- Transferts ------------------------------------------------------------------------


@router.get("/transfers", response_model=TransferPage, dependencies=[READ])
def list_transfers(
    site_id: int | None = None,
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return service.list_transfers(db, site_id, limit, offset)


@router.post(
    "/transfers",
    response_model=TransferRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[MANAGE],
)
def create_transfer(data: TransferIn, db: Session = Depends(get_db)):
    return service.create_transfer(db, data)


@router.get("/transfers/{transfer_id}", response_model=TransferRead, dependencies=[READ])
def get_transfer(transfer_id: int, db: Session = Depends(get_db)):
    return service.get_transfer(db, transfer_id)


# --- Inventaires -----------------------------------------------------------------------


@router.get("/counts", response_model=CountPage, dependencies=[READ])
def list_counts(
    status: CountStatus | None = None,
    site_id: int | None = None,
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return service.list_counts(db, status, site_id, limit, offset)


@router.post(
    "/counts", response_model=CountRead, status_code=status.HTTP_201_CREATED, dependencies=[MANAGE]
)
def create_count(data: CountCreate, db: Session = Depends(get_db)):
    """Ouvre un inventaire : photo du stock théorique du dépôt (ou d'un emplacement)."""
    return service.create_count(db, data)


@router.get("/counts/{count_id}", response_model=CountRead, dependencies=[READ])
def get_count(count_id: int, db: Session = Depends(get_db)):
    return service.get_count(db, count_id)


@router.put("/counts/{count_id}/entries", response_model=CountRead, dependencies=[COUNT])
def save_entries(count_id: int, data: CountEntries, db: Session = Depends(get_db)):
    """Saisie des quantités comptées (vide = pas encore compté)."""
    return service.save_entries(db, count_id, data)


@router.post("/counts/{count_id}/lines", response_model=CountRead, dependencies=[COUNT])
def add_count_line(count_id: int, data: CountLineAdd, db: Session = Depends(get_db)):
    """Article trouvé en rayon mais absent de la liste."""
    return service.add_count_line(db, count_id, data)


@router.post("/counts/{count_id}/validate", response_model=CountRead)
def validate_count(
    count_id: int,
    data: CountValidate,
    db: Session = Depends(get_db),
    ctx: RequestContext = MANAGE,
):
    return service.validate_count(db, ctx, count_id, data)


@router.post("/counts/{count_id}/cancel", response_model=CountRead, dependencies=[MANAGE])
def cancel_count(count_id: int, db: Session = Depends(get_db)):
    return service.cancel_count(db, count_id)
