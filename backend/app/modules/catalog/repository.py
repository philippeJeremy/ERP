"""Accès aux données du module catalog. Uniquement des requêtes, aucune règle métier.

Rappel : articles, marques et caractéristiques sont communs au groupe (pas de RLS) ;
article_suppliers et les imports sont filtrés par la RLS sur la société courante.
"""

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.modules.catalog.models import (
    Article,
    ArticleSupplier,
    Brand,
    ImportLine,
    ImportProfile,
    ImportRun,
    TireSpec,
)


def _escape(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%"


# --- Marques -------------------------------------------------------------------------


def get_brand_by_name(db: Session, name: str) -> Brand | None:
    return db.scalar(select(Brand).where(func.lower(Brand.name) == name.lower()))


def search_brands(db: Session, q: str | None, limit: int = 20) -> list[Brand]:
    query = select(Brand).order_by(Brand.name).limit(limit)
    if q:
        query = query.where(Brand.name.ilike(_escape(q)))
    return list(db.scalars(query))


# --- Articles ------------------------------------------------------------------------


def get_article(db: Session, article_id: int) -> Article | None:
    return db.get(Article, article_id)


def get_article_by_ean(db: Session, ean: str) -> Article | None:
    return db.scalar(select(Article).where(Article.ean == ean))


def articles_by_ean(db: Session, eans: list[str]) -> dict[str, Article]:
    found: dict[str, Article] = {}
    for i in range(0, len(eans), 5000):  # par paquets : la requête reste raisonnable
        chunk = eans[i : i + 5000]
        for article in db.scalars(select(Article).where(Article.ean.in_(chunk))):
            found[article.ean] = article
    return found


def _article_filters(
    query: Select,
    *,
    kind: str | None,
    q: str | None,
    size_digits: str | None,
    season: str | None,
    vehicle_type: str | None,
    partner_id: int | None,
    active: bool | None,
) -> Select:
    if kind:
        query = query.where(Article.kind == kind)
    if active is not None:
        query = query.where(Article.is_active == active)
    if season:
        query = query.where(TireSpec.season == season)
    if vehicle_type:
        query = query.where(TireSpec.vehicle_type == vehicle_type)
    if partner_id:
        query = query.where(
            select(ArticleSupplier.id)
            .where(ArticleSupplier.article_id == Article.id)
            .where(ArticleSupplier.partner_id == partner_id)
            .exists()
        )
    if q:
        pattern = _escape(q)
        conditions = [
            Article.code.ilike(pattern),
            Article.designation.ilike(pattern),
            Article.ean == q.replace(" ", ""),
            Article.manufacturer_ref.ilike(pattern),
            Brand.name.ilike(pattern),
            # Référence chez un fournisseur de la société (la RLS limite à la société).
            select(ArticleSupplier.id)
            .where(ArticleSupplier.article_id == Article.id)
            .where(ArticleSupplier.supplier_ref.ilike(pattern))
            .exists(),
        ]
        if size_digits:
            conditions.append(TireSpec.size_code.like(size_digits + "%"))
        query = query.where(or_(*conditions))
    return query


def search_articles(
    db: Session,
    *,
    kind: str | None,
    q: str | None,
    size_digits: str | None,
    season: str | None,
    vehicle_type: str | None,
    partner_id: int | None,
    active: bool | None,
    sort: str,
    descending: bool,
    limit: int,
    offset: int,
) -> tuple[list[tuple], int]:
    filters = dict(
        kind=kind,
        q=q,
        size_digits=size_digits,
        season=season,
        vehicle_type=vehicle_type,
        partner_id=partner_id,
        active=active,
    )
    base = (
        select(func.count(Article.id))
        .select_from(Article)
        .outerjoin(TireSpec)
        .outerjoin(Brand, Brand.id == Article.brand_id)
    )
    total = db.scalar(_article_filters(base, **filters)) or 0

    # Fournisseurs actifs de la société courante : nombre et meilleur prix.
    offers = (
        select(
            ArticleSupplier.article_id,
            func.count().label("supplier_count"),
            func.min(ArticleSupplier.purchase_price).label("best_price"),
        )
        .where(ArticleSupplier.is_discontinued.is_(False))
        .group_by(ArticleSupplier.article_id)
        .subquery()
    )
    query = (
        select(Article, TireSpec, Brand.name, offers.c.supplier_count, offers.c.best_price)
        .select_from(Article)
        .outerjoin(TireSpec)
        .outerjoin(Brand, Brand.id == Article.brand_id)
        .outerjoin(offers, offers.c.article_id == Article.id)
    )
    query = _article_filters(query, **filters)
    columns = {
        "code": Article.code,
        "designation": Article.designation,
        "brand": Brand.name,
        "size": TireSpec.size_code,
        "best_price": offers.c.best_price,
    }
    column = columns.get(sort, Article.designation)
    order = column.desc().nulls_last() if descending else column.asc().nulls_last()
    rows = db.execute(query.order_by(order, Article.id).limit(limit).offset(offset)).all()
    return [tuple(r) for r in rows], total


# --- Fournisseurs des articles (RLS : société courante) ---------------------------------


def get_link(db: Session, link_id: int) -> ArticleSupplier | None:
    return db.get(ArticleSupplier, link_id)


def links_of_article(db: Session, article_id: int) -> list[ArticleSupplier]:
    return list(
        db.scalars(
            select(ArticleSupplier)
            .where(ArticleSupplier.article_id == article_id)
            .order_by(
                ArticleSupplier.is_discontinued,
                ArticleSupplier.is_preferred.desc(),
                ArticleSupplier.purchase_price.nulls_last(),
            )
        )
    )


def find_link(db: Session, partner_id: int, article_id: int) -> ArticleSupplier | None:
    return db.scalar(
        select(ArticleSupplier).where(
            and_(ArticleSupplier.partner_id == partner_id, ArticleSupplier.article_id == article_id)
        )
    )


def find_link_by_ref(db: Session, partner_id: int, ref: str) -> ArticleSupplier | None:
    return db.scalar(
        select(ArticleSupplier).where(
            ArticleSupplier.partner_id == partner_id, ArticleSupplier.supplier_ref == ref
        )
    )


def links_of_partner(db: Session, partner_id: int) -> list[ArticleSupplier]:
    return list(db.scalars(select(ArticleSupplier).where(ArticleSupplier.partner_id == partner_id)))


def search_links(
    db: Session,
    *,
    partner_id: int | None,
    q: str | None,
    discontinued: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[ArticleSupplier], int]:
    query = select(ArticleSupplier).join(Article).outerjoin(Brand, Brand.id == Article.brand_id)
    if partner_id:
        query = query.where(ArticleSupplier.partner_id == partner_id)
    if discontinued is not None:
        query = query.where(ArticleSupplier.is_discontinued == discontinued)
    if q:
        pattern = _escape(q)
        query = query.where(
            or_(
                Article.designation.ilike(pattern),
                Article.code.ilike(pattern),
                Article.ean == q.replace(" ", ""),
                ArticleSupplier.supplier_ref.ilike(pattern),
                Brand.name.ilike(pattern),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(ArticleSupplier.is_discontinued, Article.designation)
        .limit(limit)
        .offset(offset)
    )
    return list(rows), total


def count_active_links(db: Session, partner_id: int) -> int:
    return (
        db.scalar(
            select(func.count(ArticleSupplier.id)).where(
                ArticleSupplier.partner_id == partner_id,
                ArticleSupplier.is_discontinued.is_(False),
            )
        )
        or 0
    )


# --- Imports -------------------------------------------------------------------------


def get_profile(db: Session, profile_id: int) -> ImportProfile | None:
    return db.get(ImportProfile, profile_id)


def list_profiles(db: Session, partner_id: int | None) -> list[ImportProfile]:
    query = select(ImportProfile).order_by(ImportProfile.name)
    if partner_id:
        query = query.where(ImportProfile.partner_id == partner_id)
    return list(db.scalars(query))


def get_run(db: Session, run_id: int, *, for_update: bool = False) -> ImportRun | None:
    query = select(ImportRun).where(ImportRun.id == run_id)
    if for_update:
        query = query.with_for_update()
    return db.scalar(query)


def list_runs(
    db: Session, partner_id: int | None, limit: int, offset: int
) -> tuple[list[ImportRun], int]:
    query = select(ImportRun)
    if partner_id:
        query = query.where(ImportRun.partner_id == partner_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(ImportRun.id.desc()).limit(limit).offset(offset))
    return list(rows), total


def run_lines(
    db: Session, run_id: int, status: str | None, limit: int | None = None, offset: int = 0
) -> tuple[list[ImportLine], int]:
    query = select(ImportLine).where(ImportLine.run_id == run_id)
    if status:
        query = query.where(ImportLine.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    query = query.order_by(ImportLine.line_no.nulls_last(), ImportLine.id).offset(offset)
    if limit:
        query = query.limit(limit)
    return list(db.scalars(query)), total
