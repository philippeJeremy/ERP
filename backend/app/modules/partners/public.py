"""Interface publique du module partners : la SEULE chose que les autres modules importent.

Exemple : le futur module articles vérifiera qu'un fournisseur existe (dans la société
courante) avant de le lier à un article, via `partners.get_supplier(db, id)`.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.modules.partners import repository as repo
from app.modules.partners.models import Partner


def get_supplier(db: Session, partner_id: int) -> Partner:
    partner = repo.get(db, partner_id)
    if partner is None or not partner.is_supplier:
        raise NotFound("Fournisseur introuvable")
    return partner


def partner_names(db: Session, ids: set[int]) -> dict[int, tuple[str, str]]:
    """{id: (code, nom)} des tiers demandés (de la société courante, grâce à la RLS)."""
    if not ids:
        return {}
    rows = db.execute(select(Partner.id, Partner.code, Partner.name).where(Partner.id.in_(ids)))
    return {row.id: (row.code, row.name) for row in rows}


__all__ = ["get_supplier", "partner_names"]
