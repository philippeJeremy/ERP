"""Interface publique du module catalog : ce que les autres modules (achats, ventes,
stock) importent pour lire un article et son prix d'achat."""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.modules.catalog import repository as repo
from app.modules.catalog.service import article_brief, get_article


@dataclass
class SupplierOffer:
    supplier_ref: str | None
    purchase_price: Decimal | None
    is_discontinued: bool


def supplier_offer(db: Session, article_id: int, partner_id: int) -> SupplierOffer | None:
    """Référence et prix de l'article chez ce fournisseur (société courante), s'il existe."""
    link = repo.find_link(db, partner_id, article_id)
    if link is None:
        return None
    return SupplierOffer(link.supplier_ref, link.purchase_price, link.is_discontinued)


def article_label(db: Session, article_id: int) -> str:
    """Désignation à reprendre sur un document : « MICHELIN 205/55 R16 91V PRIMACY 4 »."""
    article = get_article(db, article_id)
    brand = article.brand.name if article.brand else None
    label = article.designation
    if brand and brand.lower() not in label.lower():
        label = f"{brand.upper()} {label}"
    return label[:250]


__all__ = ["SupplierOffer", "article_brief", "article_label", "get_article", "supplier_offer"]
