"""Interface publique du module partners : la SEULE chose que les autres modules importent.

Exemple : le futur module articles vérifiera qu'un fournisseur existe (dans la société
courante) avant de le lier à un article, via `partners.get_supplier(db, id)`.
"""

from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.modules.partners import repository as repo
from app.modules.partners.models import Partner


def get_supplier(db: Session, partner_id: int) -> Partner:
    partner = repo.get(db, partner_id)
    if partner is None or not partner.is_supplier:
        raise NotFound("Fournisseur introuvable")
    return partner


__all__ = ["get_supplier"]
