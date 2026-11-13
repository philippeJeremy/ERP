"""Interface publique du module catalog : ce que les autres modules (achats, ventes,
stock) importent pour lire un article et son prix d'achat."""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Select
from sqlalchemy.orm import Session

from app.modules.catalog import repository as repo
from app.modules.catalog.schemas import ArticleBrief
from app.modules.catalog.service import article_brief, get_article
from app.modules.catalog.tires import search_digits


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


def article_ids_matching(q: str | None, kind: str | None = None) -> Select:
    """Sous-requête SQL des id d'articles trouvés par une recherche (code, EAN, désignation,
    marque, dimension « 2055516 »…) : à utiliser dans un `.where(x.article_id.in_(...))`."""
    q = (q or "").strip() or None
    return repo.article_ids_matching(q, kind, search_digits(q) if q else None)


def article_briefs(db: Session, ids: list[int]) -> dict[int, ArticleBrief]:
    """Fiches résumées de plusieurs articles en une requête (évite une requête par ligne)."""
    return {a.id: article_brief(a) for a in repo.articles_by_ids(db, list(set(ids)))}


__all__ = [
    "ArticleBrief",
    "article_briefs",
    "article_ids_matching",
    "SupplierOffer",
    "article_brief",
    "article_label",
    "get_article",
    "supplier_offer",
]
