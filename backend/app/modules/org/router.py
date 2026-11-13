"""Routes HTTP du module org : fines, la logique est dans le service."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.db import get_db
from app.modules.auth.public import get_context, require, require_superuser
from app.modules.org import service
from app.modules.org.schemas import (
    CompanyCreate,
    CompanyRead,
    CompanyUpdate,
    SequenceRead,
    SequenceUpdate,
    SiteIn,
    SiteRead,
    UserCompanyAccess,
)

router = APIRouter(prefix="/org", tags=["Sociétés"])


@router.get("/companies", response_model=list[CompanyRead])
def list_companies(db: Session = Depends(get_db), ctx: RequestContext = Depends(get_context)):
    """Les sociétés auxquelles l'utilisateur a accès (pour le sélecteur de société)."""
    return service.list_companies_for(db, ctx)


@router.post("/companies", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
def create_company(
    data: CompanyCreate,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(require_superuser),
):
    return service.create_company(db, ctx, data)


@router.get("/companies/{company_id}", response_model=CompanyRead)
def get_company(
    company_id: int, db: Session = Depends(get_db), ctx: RequestContext = Depends(get_context)
):
    return service.get_company(db, ctx, company_id)


@router.patch("/companies/{company_id}", response_model=CompanyRead)
def update_company(
    company_id: int,
    data: CompanyUpdate,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(require("org:manage")),
):
    return service.update_company(db, ctx, company_id, data)


@router.delete("/companies/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company(
    company_id: int,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(require_superuser),
):
    """Supprime une société vide. Avec des données : 409, la désactiver à la place."""
    service.delete_company(db, ctx, company_id)


@router.get("/user-access/{user_id}", response_model=list[UserCompanyAccess])
def user_access(
    user_id: int, db: Session = Depends(get_db), ctx: RequestContext = Depends(get_context)
):
    """À quelles sociétés (parmi les vôtres) l'utilisateur a accès, et avec quels rôles."""
    return service.user_access(db, ctx, user_id)


@router.get("/sequences", response_model=list[SequenceRead])
def list_sequences(db: Session = Depends(get_db), _=Depends(require("org:read"))):
    """Séquences de numérotation de la société courante (en-tête X-Company-Id)."""
    return service.list_sequences(db)


@router.patch("/sequences/{code}", response_model=SequenceRead)
def update_sequence(
    code: str,
    data: SequenceUpdate,
    db: Session = Depends(get_db),
    _=Depends(require("org:manage")),
):
    return service.update_sequence(db, code, data)


# --- Dépôts (lieux de livraison, futurs emplacements de stock) -----------------------


@router.get("/sites", response_model=list[SiteRead])
def list_sites(
    active: bool | None = None,
    db: Session = Depends(get_db),
    _: RequestContext = Depends(get_context),
):
    """Les dépôts de la société courante (tout utilisateur de la société : ils
    servent dans les commandes, les livraisons…)."""
    return service.list_sites(db, active)


@router.post("/sites", response_model=SiteRead, status_code=status.HTTP_201_CREATED)
def create_site(data: SiteIn, db: Session = Depends(get_db), _=Depends(require("org:manage"))):
    return service.save_site(db, data)


@router.put("/sites/{site_id}", response_model=SiteRead)
def update_site(
    site_id: int, data: SiteIn, db: Session = Depends(get_db), _=Depends(require("org:manage"))
):
    return service.save_site(db, data, site_id)


@router.delete("/sites/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_site(site_id: int, db: Session = Depends(get_db), _=Depends(require("org:manage"))):
    service.delete_site(db, site_id)
