"""Règles métier du catalogue : articles, fournisseurs des articles, profils d'import."""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, DomainError, NotFound
from app.modules.catalog import repository as repo
from app.modules.catalog.models import Article, ArticleSupplier, Brand, ImportProfile, TireSpec
from app.modules.catalog.schemas import (
    ArticleBrief,
    ArticleCreate,
    ArticleListItem,
    ArticlePage,
    ArticleSupplierIn,
    ArticleSupplierPage,
    ArticleSupplierRead,
    ArticleSupplierUpdate,
    ArticleUpdate,
    ImportProfileIn,
    PartnerBrief,
    TireSpecIn,
)
from app.modules.catalog.tires import search_digits, size_code, size_label
from app.modules.partners import public as partners


class Invalid(DomainError):
    status_code = 422
    code = "invalide"


def now() -> datetime:
    return datetime.now(UTC)


# --- Marques -------------------------------------------------------------------------


def brand_for(db: Session, name: str | None, cache: dict[str, Brand] | None = None) -> Brand | None:
    """La marque de ce nom (« michelin » = « MICHELIN »), créée si elle n'existe pas."""
    if not name or not name.strip():
        return None
    name = " ".join(name.split())
    key = name.lower()
    if cache is not None and key in cache:
        return cache[key]
    brand = repo.get_brand_by_name(db, name)
    if brand is None:
        brand = Brand(name=name)
        db.add(brand)
        db.flush()
    if cache is not None:
        cache[key] = brand
    return brand


# --- Articles ------------------------------------------------------------------------


def apply_tire(article: Article, data: TireSpecIn | dict) -> None:
    values = data.model_dump() if isinstance(data, TireSpecIn) else dict(data)
    if article.tire is None:
        article.tire = TireSpec()
    for field, value in values.items():
        if hasattr(TireSpec, field):
            setattr(article.tire, field, value)
    article.tire.size_code = size_code(
        article.tire.width, article.tire.aspect_ratio, article.tire.rim
    )


def default_designation(brand: Brand | None, tire: dict) -> str:
    """« MICHELIN 205/55 R16 91V XL » pour un pneu créé sans désignation."""
    parts = [brand.name.upper() if brand else None, size_label(tire)]
    if tire.get("reinforced"):
        parts.append("XL")
    if tire.get("runflat"):
        parts.append("RUNFLAT")
    return " ".join(p for p in parts if p) or "Pneu"


def _ensure_ean_free(db: Session, ean: str | None, article_id: int | None) -> None:
    if not ean:
        return
    other = repo.get_article_by_ean(db, ean)
    if other is not None and other.id != article_id:
        raise Conflict(
            f"Le code EAN {ean} est déjà celui de l'article {other.code} ({other.designation})",
            code="ean_existant",
        )


def get_article(db: Session, article_id: int) -> Article:
    article = repo.get_article(db, article_id)
    if article is None:
        raise NotFound("Article introuvable")
    return article


def create_article(db: Session, data: ArticleCreate) -> Article:
    _ensure_ean_free(db, data.ean, None)
    brand = brand_for(db, data.brand)
    designation = data.designation or default_designation(brand, data.tire.model_dump())
    article = Article(
        kind=data.kind,
        ean=data.ean,
        brand=brand,
        manufacturer_ref=data.manufacturer_ref,
        designation=designation,
        category=data.category,
        unit=data.unit or "U",
        notes=data.notes,
    )
    if data.tire is not None:
        apply_tire(article, data.tire)
    db.add(article)
    db.commit()
    return article


def update_article(db: Session, article_id: int, data: ArticleUpdate) -> Article:
    article = get_article(db, article_id)
    if data.version != article.version:
        raise Conflict(
            "La fiche a été modifiée entre-temps, rechargez-la", code="modifie_entre_temps"
        )
    changes = data.model_dump(exclude_unset=True, exclude={"version", "tire", "brand"})
    if "ean" in changes:
        _ensure_ean_free(db, changes["ean"], article.id)
    for field, value in changes.items():
        if value is None and field in ("designation", "is_active", "unit"):
            continue
        setattr(article, field, value)
    if "brand" in data.model_fields_set:
        article.brand = brand_for(db, data.brand)
    if data.tire is not None and article.kind == "pneu":
        apply_tire(article, data.tire)
        # La ligne tire_specs n'a pas de version : on « touche » l'article pour que le
        # verrouillage optimiste protège aussi les caractéristiques.
        article.updated_at = now()
    db.commit()
    return article


def delete_article(db: Session, article_id: int) -> None:
    article = get_article(db, article_id)
    try:
        db.delete(article)
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict(
            "Cet article a des fournisseurs (dans cette société ou une autre) ou des documents : "
            "il ne peut pas être supprimé. Désactivez-le à la place.",
            code="article_utilise",
        ) from exc
    db.commit()


def list_articles(db: Session, **filters) -> ArticlePage:
    q = (filters.get("q") or "").strip() or None
    rows, total = repo.search_articles(
        db,
        kind=filters["kind"],
        q=q,
        size_digits=search_digits(q) if q else None,
        season=filters["season"],
        vehicle_type=filters["vehicle_type"],
        partner_id=filters["partner_id"],
        active=filters["active"],
        sort=filters["sort"],
        descending=filters["order"] == "desc",
        limit=filters["limit"],
        offset=filters["offset"],
    )
    items = []
    for article, tire, brand, count, best in rows:
        spec = (
            {
                c: getattr(tire, c)
                for c in (
                    "width",
                    "aspect_ratio",
                    "rim",
                    "construction",
                    "load_index",
                    "speed_index",
                )
            }
            if tire
            else {}
        )
        items.append(
            ArticleListItem(
                id=article.id,
                code=article.code,
                kind=article.kind,
                ean=article.ean,
                brand=brand,
                designation=article.designation,
                size=size_label(spec) if tire else None,
                season=tire.season if tire else None,
                vehicle_type=tire.vehicle_type if tire else None,
                fuel_class=tire.fuel_class if tire else None,
                wet_class=tire.wet_class if tire else None,
                noise_db=tire.noise_db if tire else None,
                is_active=article.is_active,
                supplier_count=count or 0,
                best_price=best,
            )
        )
    return ArticlePage(items=items, total=total)


# --- Fournisseurs des articles (propres à la société courante) --------------------------


def article_brief(article: Article) -> ArticleBrief:
    spec = None
    if article.tire is not None:
        spec = size_label(
            {
                c: getattr(article.tire, c)
                for c in (
                    "width",
                    "aspect_ratio",
                    "rim",
                    "construction",
                    "load_index",
                    "speed_index",
                )
            }
        )
    return ArticleBrief(
        id=article.id,
        code=article.code,
        designation=article.designation,
        ean=article.ean,
        brand=article.brand.name if article.brand else None,
        size=spec,
    )


def links_read(db: Session, links: list[ArticleSupplier]) -> list[ArticleSupplierRead]:
    names = partners.partner_names(db, {link.partner_id for link in links})
    return [
        ArticleSupplierRead(
            id=link.id,
            article=article_brief(link.article),
            partner=PartnerBrief(
                id=link.partner_id,
                code=names.get(link.partner_id, ("?", "?"))[0],
                name=names.get(link.partner_id, ("?", "Tiers inconnu"))[1],
            ),
            supplier_ref=link.supplier_ref,
            purchase_price=link.purchase_price,
            currency=link.currency,
            is_preferred=link.is_preferred,
            is_discontinued=link.is_discontinued,
            discontinued_at=link.discontinued_at,
            price_updated_at=link.price_updated_at,
            version=link.version,
        )
        for link in links
    ]


def article_suppliers(db: Session, article_id: int) -> list[ArticleSupplierRead]:
    get_article(db, article_id)
    return links_read(db, repo.links_of_article(db, article_id))


def search_links(db: Session, **filters) -> ArticleSupplierPage:
    links, total = repo.search_links(db, **filters)
    return ArticleSupplierPage(items=links_read(db, links), total=total)


def _unset_other_preferred(db: Session, link: ArticleSupplier) -> None:
    for other in repo.links_of_article(db, link.article_id):
        if other.id != link.id and other.is_preferred:
            other.is_preferred = False


def add_supplier(db: Session, article_id: int, data: ArticleSupplierIn) -> ArticleSupplierRead:
    article = get_article(db, article_id)
    partners.get_supplier(db, data.partner_id)  # existe, dans la société, et fournisseur
    if repo.find_link(db, data.partner_id, article.id):
        raise Conflict("Ce fournisseur est déjà lié à l'article", code="fournisseur_deja_lie")
    if data.supplier_ref and repo.find_link_by_ref(db, data.partner_id, data.supplier_ref):
        raise Conflict(
            f"La référence « {data.supplier_ref} » est déjà utilisée chez ce fournisseur",
            code="reference_existante",
        )
    link = ArticleSupplier(
        article=article,
        price_updated_at=now() if data.purchase_price is not None else None,
        **data.model_dump(),
    )
    db.add(link)
    db.flush()
    if link.is_preferred:
        _unset_other_preferred(db, link)
    db.commit()
    return links_read(db, [link])[0]


def update_supplier_link(
    db: Session, link_id: int, data: ArticleSupplierUpdate
) -> ArticleSupplierRead:
    link = repo.get_link(db, link_id)
    if link is None:
        raise NotFound("Lien article-fournisseur introuvable")
    if data.version != link.version:
        raise Conflict("Modifié entre-temps, rechargez", code="modifie_entre_temps")
    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    if changes.get("supplier_ref") and changes["supplier_ref"] != link.supplier_ref:
        other = repo.find_link_by_ref(db, link.partner_id, changes["supplier_ref"])
        if other is not None and other.id != link.id:
            raise Conflict(
                "Référence déjà utilisée chez ce fournisseur", code="reference_existante"
            )
    if "purchase_price" in changes and changes["purchase_price"] != link.purchase_price:
        link.price_updated_at = now()
    if "is_discontinued" in changes and changes["is_discontinued"] != link.is_discontinued:
        link.discontinued_at = now() if changes["is_discontinued"] else None
    for field, value in changes.items():
        if value is None and field in ("is_preferred", "is_discontinued"):
            continue
        setattr(link, field, value)
    if link.is_preferred:
        _unset_other_preferred(db, link)
    db.commit()
    return links_read(db, [link])[0]


def delete_supplier_link(db: Session, link_id: int) -> None:
    link = repo.get_link(db, link_id)
    if link is None:
        raise NotFound("Lien article-fournisseur introuvable")
    db.delete(link)
    db.commit()


# --- Profils d'import ----------------------------------------------------------------


def list_profiles(db: Session, partner_id: int | None) -> list[ImportProfile]:
    return repo.list_profiles(db, partner_id)


def get_profile(db: Session, profile_id: int) -> ImportProfile:
    profile = repo.get_profile(db, profile_id)
    if profile is None:
        raise NotFound("Profil d'import introuvable")
    return profile


def save_profile(
    db: Session, data: ImportProfileIn, profile_id: int | None = None
) -> ImportProfile:
    partners.get_supplier(db, data.partner_id)
    profile = get_profile(db, profile_id) if profile_id else ImportProfile()
    for field, value in data.model_dump().items():
        setattr(profile, field, value)
    if profile_id is None:
        db.add(profile)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict(
            f"Ce fournisseur a déjà un profil nommé « {data.name} »", code="profil_existant"
        ) from exc
    return profile


def delete_profile(db: Session, profile_id: int) -> None:
    db.delete(get_profile(db, profile_id))
    db.commit()
