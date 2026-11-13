"""Accès aux tables `inventory.*` (la RLS limite tout à la société courante)."""

from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.inventory.models import (
    ArticleCost,
    Count,
    CountLine,
    Location,
    Reservation,
    StockLevel,
    StockMove,
    Transfer,
)

# DOT « WWYY » → clé « YYWW » pour trier dans l'ordre chronologique (« 5224 », semaine 52
# de 2024, passe avant « 0125 »). NULL pour les articles sans DOT (triés en dernier).
DOT_ORDER = func.nullif(
    func.concat(func.substr(StockLevel.dot, 3, 2), func.substr(StockLevel.dot, 1, 2)), ""
)


def dot_key(dot: str) -> str:
    """Clé de tri Python équivalente : « 2324 » → « 2423 », sans DOT à la fin."""
    return dot[2:] + dot[:2] if dot else "9999"


# --- Emplacements ----------------------------------------------------------------------


def get_location(db: Session, location_id: int) -> Location | None:
    return db.get(Location, location_id)


def list_locations(db: Session, site_id: int, active: bool | None = None) -> list[Location]:
    query = select(Location).where(Location.site_id == site_id)
    if active is not None:
        query = query.where(Location.is_active == active)
    return list(db.scalars(query.order_by(Location.is_default.desc(), Location.code)))


def default_location(db: Session, site_id: int) -> Location | None:
    return db.scalar(select(Location).where(Location.site_id == site_id, Location.is_default))


def location_by_code(db: Session, site_id: int, code: str) -> Location | None:
    return db.scalar(select(Location).where(Location.site_id == site_id, Location.code == code))


def locations_by_ids(db: Session, ids: set[int]) -> dict[int, Location]:
    if not ids:
        return {}
    return {x.id: x for x in db.scalars(select(Location).where(Location.id.in_(ids)))}


def location_in_use(db: Session, location_id: int) -> bool:
    used = select(StockMove.id).where(StockMove.location_id == location_id).exists()
    return bool(db.scalar(select(used)))


# --- Niveaux de stock ------------------------------------------------------------------


def lock_level(db: Session, location: Location, article_id: int, dot: str) -> StockLevel:
    """La ligne de stock, verrouillée jusqu'au commit ; créée à zéro si elle n'existe pas.

    Le verrou (SELECT … FOR UPDATE) empêche deux sorties simultanées de vendre deux fois
    le même pneu : la seconde attend la fin de la première et voit le stock à jour.
    """
    query = select(StockLevel).where(
        StockLevel.location_id == location.id,
        StockLevel.article_id == article_id,
        StockLevel.dot == dot,
    )
    level = db.scalar(query.with_for_update())
    if level is None:
        # INSERT … ON CONFLICT DO NOTHING : si un autre utilisateur crée la même ligne au
        # même instant, pas d'erreur ; on relit ensuite (avec verrou).
        db.execute(
            insert(StockLevel)
            .values(
                article_id=article_id,
                site_id=location.site_id,
                location_id=location.id,
                dot=dot,
                quantity=0,
            )
            .on_conflict_do_nothing()
        )
        level = db.scalar(query.with_for_update().execution_options(populate_existing=True))
    assert level is not None
    return level


def levels_fifo(db: Session, location_id: int, article_id: int) -> list[StockLevel]:
    """Les lots en stock à un emplacement, du DOT le plus ancien au plus récent, verrouillés."""
    query = (
        select(StockLevel)
        .where(
            StockLevel.location_id == location_id,
            StockLevel.article_id == article_id,
            StockLevel.quantity > 0,
        )
        .order_by(DOT_ORDER.asc().nulls_last(), StockLevel.id)
        .with_for_update()
    )
    return list(db.scalars(query))


def company_quantity(db: Session, article_id: int) -> Decimal:
    """Quantité totale de l'article dans la société (tous dépôts) : base du CMP."""
    total = db.scalar(
        select(func.coalesce(func.sum(StockLevel.quantity), 0)).where(
            StockLevel.article_id == article_id
        )
    )
    return Decimal(total)


def levels_of_article(db: Session, article_id: int) -> list[StockLevel]:
    query = select(StockLevel).where(StockLevel.article_id == article_id, StockLevel.quantity > 0)
    return list(db.scalars(query))


def levels_for_count(db: Session, site_id: int, location_id: int | None) -> list[StockLevel]:
    query = select(StockLevel).where(StockLevel.site_id == site_id, StockLevel.quantity > 0)
    if location_id is not None:
        query = query.where(StockLevel.location_id == location_id)
    return list(db.scalars(query.order_by(StockLevel.location_id, StockLevel.article_id)))


def stock_page(
    db: Session,
    *,
    site_id: int | None,
    location_id: int | None,
    articles: Select | None,
    sort: str,
    descending: bool,
    limit: int,
    offset: int,
) -> tuple[list[tuple], int, Decimal, Decimal]:
    """État du stock agrégé par article : (article_id, quantité, CMP, valeur, plus vieux DOT)."""
    cost = func.coalesce(ArticleCost.average_cost, 0)
    quantity = func.sum(StockLevel.quantity)
    oldest = func.min(DOT_ORDER)
    query = (
        select(
            StockLevel.article_id,
            quantity.label("quantity"),
            cost.label("cost"),
            (quantity * cost).label("value"),
            oldest.label("oldest"),
        )
        .outerjoin(
            ArticleCost,
            (ArticleCost.article_id == StockLevel.article_id)
            & (ArticleCost.company_id == StockLevel.company_id),
        )
        .where(StockLevel.quantity > 0)
        .group_by(StockLevel.article_id, ArticleCost.average_cost)
    )
    if site_id is not None:
        query = query.where(StockLevel.site_id == site_id)
    if location_id is not None:
        query = query.where(StockLevel.location_id == location_id)
    if articles is not None:
        query = query.where(StockLevel.article_id.in_(articles))
    grouped = query.subquery()
    total, total_qty, total_value = db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(grouped.c.quantity), 0),
            func.coalesce(func.sum(grouped.c.value), 0),
        )
    ).one()
    columns = {
        "quantity": grouped.c.quantity,
        "value": grouped.c.value,
        "cost": grouped.c.cost,
        "dot": grouped.c.oldest,
    }
    column = columns.get(sort, grouped.c.value)
    order = column.desc().nulls_last() if descending else column.asc().nulls_last()
    rows = db.execute(
        select(grouped).order_by(order, grouped.c.article_id).limit(limit).offset(offset)
    ).all()
    return [tuple(r) for r in rows], total, Decimal(total_qty), Decimal(total_value)


# --- Coût moyen pondéré ----------------------------------------------------------------


def lock_cost_by_article(db: Session, article_id: int) -> ArticleCost | None:
    """La RLS ne laisse voir que la ligne de la société courante."""
    query = select(ArticleCost).where(ArticleCost.article_id == article_id)
    return db.scalar(query.with_for_update().execution_options(populate_existing=True))


def get_cost(db: Session, article_id: int) -> Decimal:
    value = db.scalar(select(ArticleCost.average_cost).where(ArticleCost.article_id == article_id))
    return value if value is not None else Decimal(0)


def costs_of(db: Session, article_ids: set[int]) -> dict[int, Decimal]:
    if not article_ids:
        return {}
    rows = db.execute(
        select(ArticleCost.article_id, ArticleCost.average_cost).where(
            ArticleCost.article_id.in_(article_ids)
        )
    )
    return {a: c for a, c in rows}


# --- Mouvements ------------------------------------------------------------------------


def search_moves(
    db: Session,
    *,
    article_id: int | None,
    site_id: int | None,
    kind: str | None,
    source: str | None,
    articles: Select | None,
    limit: int,
    offset: int,
) -> tuple[list[StockMove], int]:
    query = select(StockMove)
    if article_id is not None:
        query = query.where(StockMove.article_id == article_id)
    if site_id is not None:
        query = query.where(StockMove.site_id == site_id)
    if kind:
        query = query.where(StockMove.kind == kind)
    if source:
        query = query.where(StockMove.source == source)
    if articles is not None:
        query = query.where(StockMove.article_id.in_(articles))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(StockMove.moved_at.desc(), StockMove.id.desc()).limit(limit).offset(offset)
    )
    return list(rows), total


def moves_of_source(db: Session, source: str) -> list[StockMove]:
    return list(
        db.scalars(select(StockMove).where(StockMove.source == source).order_by(StockMove.id))
    )


# --- Transferts ------------------------------------------------------------------------


def get_transfer(db: Session, transfer_id: int) -> Transfer | None:
    return db.get(Transfer, transfer_id)


def list_transfers(
    db: Session, site_id: int | None, limit: int, offset: int
) -> tuple[list[tuple[Transfer, int, Decimal]], int]:
    query = select(Transfer)
    if site_id is not None:
        query = query.where((Transfer.from_site_id == site_id) | (Transfer.to_site_id == site_id))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    transfers = list(
        db.scalars(
            query.order_by(Transfer.transferred_on.desc(), Transfer.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    stats = dict.fromkeys([f"transfer:{t.id}" for t in transfers], (0, Decimal(0)))
    if transfers:
        rows = db.execute(
            select(StockMove.source, func.count(), func.sum(StockMove.quantity))
            .where(StockMove.source.in_(list(stats)), StockMove.quantity > 0)
            .group_by(StockMove.source)
        )
        stats.update({s: (c, q) for s, c, q in rows})
    return [(t, *stats[f"transfer:{t.id}"]) for t in transfers], total


# --- Inventaires -----------------------------------------------------------------------


def get_count(db: Session, count_id: int, *, for_update: bool = False) -> Count | None:
    query = select(Count).where(Count.id == count_id)
    if for_update:
        query = query.with_for_update(of=Count)
    return db.scalar(query)


def list_counts(
    db: Session, status: str | None, site_id: int | None, limit: int, offset: int
) -> tuple[list[tuple[Count, int, int]], int]:
    query = select(Count)
    if status:
        query = query.where(Count.status == status)
    if site_id is not None:
        query = query.where(Count.site_id == site_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    counts = list(db.scalars(query.order_by(Count.id.desc()).limit(limit).offset(offset)))
    stats: dict[int, tuple[int, int]] = {c.id: (0, 0) for c in counts}
    if counts:
        rows = db.execute(
            select(CountLine.count_id, func.count(), func.count(CountLine.counted_qty))
            .where(CountLine.count_id.in_(list(stats)))
            .group_by(CountLine.count_id)
        )
        stats.update({i: (n, c) for i, n, c in rows})
    return [(c, *stats[c.id]) for c in counts], total


def open_count_on(db: Session, site_id: int) -> Count | None:
    return db.scalar(
        select(Count).where(Count.site_id == site_id, Count.status == "en_cours").limit(1)
    )


# --- Réservations et sorties ------------------------------------------------------------


def get_reservation(db: Session, source: str) -> Reservation | None:
    return db.scalar(select(Reservation).where(Reservation.source == source))


def reserved_by(db: Session, article_ids: set[int], site_id: int | None) -> dict[int, Decimal]:
    if not article_ids:
        return {}
    query = (
        select(Reservation.article_id, func.sum(Reservation.quantity))
        .where(Reservation.article_id.in_(article_ids))
        .group_by(Reservation.article_id)
    )
    if site_id is not None:
        query = query.where(Reservation.site_id == site_id)
    return {a: q for a, q in db.execute(query)}


def on_hand_by(db: Session, article_ids: set[int], site_id: int | None) -> dict[int, Decimal]:
    if not article_ids:
        return {}
    query = (
        select(StockLevel.article_id, func.sum(StockLevel.quantity))
        .where(StockLevel.article_id.in_(article_ids))
        .group_by(StockLevel.article_id)
    )
    if site_id is not None:
        query = query.where(StockLevel.site_id == site_id)
    return {a: q for a, q in db.execute(query)}


def reserved_by_site(db: Session, article_id: int) -> dict[int, Decimal]:
    rows = db.execute(
        select(Reservation.site_id, func.sum(Reservation.quantity))
        .where(Reservation.article_id == article_id)
        .group_by(Reservation.site_id)
    )
    return {s: q for s, q in rows}


def site_levels_fifo(
    db: Session, site_id: int, article_id: int, location_id: int | None, dot: str | None
) -> list[StockLevel]:
    """Lots d'un article dans un dépôt, du DOT le plus ancien au plus récent, verrouillés.
    À DOT égal, l'emplacement par défaut (le quai) passe en dernier : on vide d'abord
    les rayons."""
    query = (
        select(StockLevel)
        .join(Location, Location.id == StockLevel.location_id)
        .where(
            StockLevel.site_id == site_id,
            StockLevel.article_id == article_id,
            StockLevel.quantity > 0,
        )
    )
    if location_id is not None:
        query = query.where(StockLevel.location_id == location_id)
    if dot is not None:
        query = query.where(StockLevel.dot == dot)
    query = query.order_by(
        DOT_ORDER.asc().nulls_last(), Location.is_default, Location.code, StockLevel.id
    ).with_for_update(of=StockLevel)
    return list(db.scalars(query))
