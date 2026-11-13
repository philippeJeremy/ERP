"""Routes HTTP du module partners. La société est celle de l'en-tête X-Company-Id."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.auth.public import require
from app.modules.partners import service
from app.modules.partners.schemas import (
    AddressIn,
    AddressRead,
    ContactIn,
    ContactRead,
    PartnerCreate,
    PartnerPage,
    PartnerRead,
    PartnerUpdate,
)

router = APIRouter(prefix="/partners", tags=["Tiers"])

READ = Depends(require("partners:read"))
MANAGE = Depends(require("partners:manage"))


@router.get("", response_model=PartnerPage, dependencies=[READ])
def list_partners(
    role: Literal["supplier", "customer"] | None = None,
    q: str | None = Query(None, max_length=100, description="Code, nom, SIRET, e-mail ou contact"),
    active: bool | None = None,
    sort: Literal["code", "name", "created_at"] = "name",
    order: Literal["asc", "desc"] = "asc",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Liste paginée : `items` (une page) et `total` (pour la pagination)."""
    return service.list_partners(
        db, role=role, q=q, active=active, sort=sort, order=order, limit=limit, offset=offset
    )


@router.post(
    "", response_model=PartnerRead, status_code=status.HTTP_201_CREATED, dependencies=[MANAGE]
)
def create_partner(data: PartnerCreate, db: Session = Depends(get_db)):
    return service.create_partner(db, data)


@router.get("/{partner_id}", response_model=PartnerRead, dependencies=[READ])
def get_partner(partner_id: int, db: Session = Depends(get_db)):
    return service.get_partner(db, partner_id)


@router.patch("/{partner_id}", response_model=PartnerRead, dependencies=[MANAGE])
def update_partner(partner_id: int, data: PartnerUpdate, db: Session = Depends(get_db)):
    return service.update_partner(db, partner_id, data)


@router.delete("/{partner_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[MANAGE])
def delete_partner(partner_id: int, db: Session = Depends(get_db)):
    """Supprime un tiers sans historique. Sinon 409 : le désactiver à la place."""
    service.delete_partner(db, partner_id)


@router.post(
    "/{partner_id}/addresses",
    response_model=AddressRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[MANAGE],
)
def add_address(partner_id: int, data: AddressIn, db: Session = Depends(get_db)):
    return service.add_address(db, partner_id, data)


@router.put(
    "/{partner_id}/addresses/{address_id}", response_model=AddressRead, dependencies=[MANAGE]
)
def update_address(
    partner_id: int, address_id: int, data: AddressIn, db: Session = Depends(get_db)
):
    return service.update_address(db, partner_id, address_id, data)


@router.delete(
    "/{partner_id}/addresses/{address_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[MANAGE],
)
def delete_address(partner_id: int, address_id: int, db: Session = Depends(get_db)):
    service.delete_address(db, partner_id, address_id)


@router.post(
    "/{partner_id}/contacts",
    response_model=ContactRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[MANAGE],
)
def add_contact(partner_id: int, data: ContactIn, db: Session = Depends(get_db)):
    return service.add_contact(db, partner_id, data)


@router.put(
    "/{partner_id}/contacts/{contact_id}", response_model=ContactRead, dependencies=[MANAGE]
)
def update_contact(
    partner_id: int, contact_id: int, data: ContactIn, db: Session = Depends(get_db)
):
    return service.update_contact(db, partner_id, contact_id, data)


@router.delete(
    "/{partner_id}/contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[MANAGE],
)
def delete_contact(partner_id: int, contact_id: int, db: Session = Depends(get_db)):
    service.delete_contact(db, partner_id, contact_id)
