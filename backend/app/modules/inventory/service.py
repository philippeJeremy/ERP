"""Règles métier du stock.

Tout changement de stock passe par `_move()` : verrou de la ligne de stock, contrôle
« jamais négatif », écriture au journal et, pour une entrée achetée, recalcul du CMP.
Les fonctions publiques (ajuster, transférer, valider un inventaire, réceptionner)
font un seul `commit` à la fin : tout passe, ou rien.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.errors import Conflict, DomainError, NotFound
from app.modules.catalog import public as catalog
from app.modules.inventory import repository as repo
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
from app.modules.inventory.schemas import (
    AdjustIn,
    ArticleStock,
    CountCreate,
    CountEntries,
    CountLineAdd,
    CountLineView,
    CountListItem,
    CountPage,
    CountRead,
    CountValidate,
    LevelRead,
    LocationBrief,
    LocationIn,
    MovePage,
    MoveRead,
    SiteAvailability,
    SiteBrief,
    StockPage,
    StockRow,
    TransferIn,
    TransferListItem,
    TransferPage,
    TransferRead,
)
from app.modules.org import public as org

COST = Decimal("0.0001")
CENT = Decimal("0.01")
DEFAULT_LOCATION = ("QUAI", "Quai de réception")


class Invalid(DomainError):
    status_code = 422
    code = "invalide"


class InsufficientStock(DomainError):
    status_code = 409
    code = "stock_insuffisant"


def now() -> datetime:
    return datetime.now(UTC)


def _qty(value: Decimal) -> str:
    """Quantité lisible : 4 et pas 4.000."""
    return f"{value.normalize():f}"


# --- Emplacements ----------------------------------------------------------------------


def ensure_default_location(db: Session, site_id: int) -> Location:
    """L'emplacement par défaut du dépôt (quai de réception), créé au premier besoin."""
    location = repo.default_location(db, site_id)
    if location is None:
        org.get_site(db, site_id)  # le dépôt existe et appartient à la société
        location = repo.location_by_code(db, site_id, DEFAULT_LOCATION[0])
        if location is None:
            location = Location(site_id=site_id, code=DEFAULT_LOCATION[0], name=DEFAULT_LOCATION[1])
            db.add(location)
        location.is_default = True
        location.is_active = True
        db.flush()
    return location


def list_locations(db: Session, site_id: int, active: bool | None = None) -> list[Location]:
    ensure_default_location(db, site_id)
    locations = repo.list_locations(db, site_id, active)
    db.commit()
    return locations


def get_location(db: Session, location_id: int) -> Location:
    location = repo.get_location(db, location_id)
    if location is None:
        raise NotFound("Emplacement introuvable")
    return location


def _location_of_site(db: Session, location_id: int | None, site_id: int) -> Location:
    """L'emplacement demandé (qui doit être dans ce dépôt), ou celui par défaut."""
    if location_id is None:
        return ensure_default_location(db, site_id)
    location = get_location(db, location_id)
    if location.site_id != site_id:
        raise Invalid(f"L'emplacement {location.code} n'est pas dans ce dépôt")
    return location


def save_location(
    db: Session, data: LocationIn, *, site_id: int | None = None, location_id: int | None = None
) -> Location:
    if location_id is not None:
        location = get_location(db, location_id)
        site_id = location.site_id
    else:
        assert site_id is not None
        org.get_site(db, site_id)
        ensure_default_location(db, site_id)
        location = Location(site_id=site_id, is_default=False)
    other = repo.location_by_code(db, site_id, data.code)
    if other is not None and other.id != location.id:
        raise Conflict(f"L'emplacement « {data.code} » existe déjà", code="code_existant")
    if location.is_default and not data.is_default:
        raise Invalid("Choisissez un autre emplacement par défaut au lieu de retirer celui-ci")
    if data.is_default and not data.is_active:
        raise Invalid("L'emplacement par défaut doit rester actif")
    location.code = data.code
    location.name = data.name
    location.is_active = data.is_active
    if location_id is None:
        db.add(location)
    if data.is_default and not location.is_default:
        current = repo.default_location(db, site_id)
        if current is not None:
            current.is_default = False
            db.flush()  # l'index « un seul par défaut » est vérifié ligne par ligne
        location.is_default = True
    db.commit()
    return location


def delete_location(db: Session, location_id: int) -> None:
    location = get_location(db, location_id)
    if location.is_default:
        raise Invalid("L'emplacement par défaut ne peut pas être supprimé")
    if repo.location_in_use(db, location_id):
        raise Conflict(
            "Cet emplacement a déjà eu du stock : désactivez-le plutôt.",
            code="emplacement_utilise",
        )
    db.delete(location)
    db.commit()


# --- Le cœur : un mouvement ------------------------------------------------------------


def _lock_cost(db: Session, article_id: int) -> ArticleCost:
    """Verrouille le coût de l'article : les mouvements d'un même article passent un par un,
    ce qui garde le CMP exact même si deux réceptions arrivent à la même seconde."""
    cost = repo.lock_cost_by_article(db, article_id)
    if cost is None:
        db.execute(
            insert(ArticleCost)
            .values(article_id=article_id, average_cost=0)
            .on_conflict_do_nothing()
        )
        cost = repo.lock_cost_by_article(db, article_id)
    assert cost is not None
    return cost


@dataclass
class _Move:
    kind: str
    article_id: int
    location: Location
    dot: str
    quantity: Decimal  # + entrée, − sortie
    unit_cost: Decimal | None = None  # entrée achetée : coût d'achat net. Sinon : CMP du moment
    source: str | None = None
    reference: str | None = None
    reason: str | None = None
    note: str | None = None
    moved_at: datetime | None = None


def _move(db: Session, m: _Move) -> StockMove:
    if not m.location.is_active and m.quantity > 0:
        raise Invalid(f"L'emplacement {m.location.code} est désactivé")
    cost = _lock_cost(db, m.article_id)
    level = repo.lock_level(db, m.location, m.article_id, m.dot)
    if m.quantity < 0 and level.quantity + m.quantity < 0:
        article = catalog.article_brief(catalog.get_article(db, m.article_id))
        dot = f", DOT {m.dot}" if m.dot else ""
        raise InsufficientStock(
            f"Stock insuffisant pour {article.code} à l'emplacement {m.location.code}{dot} : "
            f"{_qty(level.quantity)} en stock, {_qty(-m.quantity)} demandés"
        )
    if m.unit_cost is not None and m.quantity > 0:
        # Coût moyen pondéré : (stock × ancien CMP + entrée × coût) / (stock + entrée).
        # Stock calculé sur toute la société, AVANT l'entrée.
        before = repo.company_quantity(db, m.article_id)
        if before <= 0:
            cost.average_cost = m.unit_cost.quantize(COST, rounding=ROUND_HALF_UP)
        else:
            total = before * cost.average_cost + m.quantity * m.unit_cost
            cost.average_cost = (total / (before + m.quantity)).quantize(
                COST, rounding=ROUND_HALF_UP
            )
        unit_cost = m.unit_cost
    else:
        unit_cost = cost.average_cost
    level.quantity += m.quantity
    move = StockMove(
        kind=m.kind,
        article_id=m.article_id,
        site_id=m.location.site_id,
        location_id=m.location.id,
        dot=m.dot,
        quantity=m.quantity,
        unit_cost=unit_cost,
        source=m.source,
        reference=m.reference,
        reason=m.reason,
        note=m.note,
    )
    if m.moved_at is not None:
        move.moved_at = m.moved_at
    db.add(move)
    db.flush()
    return move


def _take_fifo(
    db: Session, location: Location, article_id: int, quantity: Decimal
) -> list[tuple[str, Decimal]]:
    """Répartit une sortie sur les DOT les plus anciens d'abord : [(dot, quantité), …]."""
    parts: list[tuple[str, Decimal]] = []
    remaining = quantity
    for level in repo.levels_fifo(db, location.id, article_id):
        if remaining <= 0:
            break
        take = min(level.quantity, remaining)
        parts.append((level.dot, take))
        remaining -= take
    if remaining > 0:
        article = catalog.article_brief(catalog.get_article(db, article_id))
        available = quantity - remaining
        raise InsufficientStock(
            f"Stock insuffisant pour {article.code} à l'emplacement {location.code} : "
            f"{_qty(available)} en stock, {_qty(quantity)} demandés"
        )
    return parts


# --- Entrée par réception (appelée par le module achats) ------------------------------


def receive(
    db: Session,
    *,
    article_id: int,
    site_id: int,
    location_id: int | None,
    dot: str,
    quantity: Decimal,
    unit_cost: Decimal,
    source: str,
    reference: str,
) -> int:
    """Entrée en stock d'une réception fournisseur. NE COMMITE PAS : c'est la réception
    (module achats) qui valide l'ensemble. Renvoie l'id de l'emplacement utilisé."""
    location = _location_of_site(db, location_id, site_id)
    _move(
        db,
        _Move(
            kind="reception",
            article_id=article_id,
            location=location,
            dot=dot,
            quantity=quantity,
            unit_cost=unit_cost,
            source=source,
            reference=reference,
        ),
    )
    return location.id


# --- Ajustement ------------------------------------------------------------------------


def adjust(db: Session, data: AdjustIn) -> MoveRead:
    location = get_location(db, data.location_id)
    catalog.get_article(db, data.article_id)
    if data.unit_cost is not None and data.quantity < 0:
        raise Invalid("Un coût ne s'indique que pour une entrée (la sortie part au CMP)")
    move = _move(
        db,
        _Move(
            kind="ajustement",
            article_id=data.article_id,
            location=location,
            dot=data.dot,
            quantity=data.quantity,
            unit_cost=data.unit_cost,
            reason=data.reason,
            note=data.note,
        ),
    )
    db.commit()
    return _moves_read(db, [move])[0]


# --- Transferts ------------------------------------------------------------------------


def create_transfer(db: Session, data: TransferIn) -> TransferRead:
    if data.from_site_id == data.to_site_id:
        raise Invalid("Les dépôts de départ et d'arrivée doivent être différents")
    org.get_site(db, data.from_site_id)
    org.get_site(db, data.to_site_id)
    transfer = Transfer(
        number=org.next_number(db, "transfer"),
        from_site_id=data.from_site_id,
        to_site_id=data.to_site_id,
        transferred_on=data.transferred_on,
        note=data.note,
    )
    db.add(transfer)
    db.flush()
    source = f"transfer:{transfer.id}"
    for line in data.lines:
        catalog.get_article(db, line.article_id)
        origin = _location_of_site(db, line.from_location_id, data.from_site_id)
        target = _location_of_site(db, line.to_location_id, data.to_site_id)
        if line.dot is None:
            parts = _take_fifo(db, origin, line.article_id, line.quantity)
        else:
            parts = [(line.dot, line.quantity)]
        for dot, quantity in parts:
            common = dict(
                kind="transfert",
                article_id=line.article_id,
                dot=dot,
                source=source,
                reference=transfer.number,
            )
            _move(db, _Move(location=origin, quantity=-quantity, **common))
            # Le CMP est celui de la société : il ne change pas lors d'un transfert.
            _move(db, _Move(location=target, quantity=quantity, **common))
    db.commit()
    return get_transfer(db, transfer.id)


def _transfer_item(
    transfer: Transfer, sites: dict[int, SiteBrief], count: int, quantity: Decimal
) -> dict:
    return dict(
        id=transfer.id,
        number=transfer.number,
        from_site=sites[transfer.from_site_id],
        to_site=sites[transfer.to_site_id],
        transferred_on=transfer.transferred_on,
        note=transfer.note,
        line_count=count,
        total_quantity=quantity,
        created_at=transfer.created_at,
    )


def list_transfers(db: Session, site_id: int | None, limit: int, offset: int) -> TransferPage:
    rows, total = repo.list_transfers(db, site_id, limit, offset)
    sites = _sites(db)
    return TransferPage(
        items=[TransferListItem(**_transfer_item(t, sites, c, q)) for t, c, q in rows],
        total=total,
    )


def get_transfer(db: Session, transfer_id: int) -> TransferRead:
    transfer = repo.get_transfer(db, transfer_id)
    if transfer is None:
        raise NotFound("Transfert introuvable")
    moves = repo.moves_of_source(db, f"transfer:{transfer.id}")
    entries = [m for m in moves if m.quantity > 0]
    quantity = sum((m.quantity for m in entries), Decimal(0))
    return TransferRead(
        **_transfer_item(transfer, _sites(db), len(entries), quantity),
        moves=_moves_read(db, moves),
    )


# --- Inventaires -----------------------------------------------------------------------


def create_count(db: Session, data: CountCreate) -> CountRead:
    org.get_site(db, data.site_id)
    location = None
    if data.location_id is not None:
        location = _location_of_site(db, data.location_id, data.site_id)
    current = repo.open_count_on(db, data.site_id)
    if current is not None:
        raise Conflict(
            f"L'inventaire {current.number} est déjà en cours sur ce dépôt : "
            "validez-le ou annulez-le d'abord.",
            code="inventaire_en_cours",
        )
    count = Count(
        number=org.next_number(db, "stock_count"),
        site_id=data.site_id,
        location_id=location.id if location else None,
        note=data.note,
    )
    # Photo du stock théorique au moment de l'ouverture.
    for level in repo.levels_for_count(db, data.site_id, count.location_id):
        count.lines.append(
            CountLine(
                article_id=level.article_id,
                location_id=level.location_id,
                dot=level.dot,
                expected_qty=level.quantity,
            )
        )
    db.add(count)
    db.commit()
    return get_count(db, count.id)


def _count(db: Session, count_id: int, *, for_update: bool = False) -> Count:
    count = repo.get_count(db, count_id, for_update=for_update)
    if count is None:
        raise NotFound("Inventaire introuvable")
    return count


def _open(count: Count, action: str) -> None:
    if count.status != "en_cours":
        label = "validé" if count.status == "valide" else "annulé"
        raise Conflict(
            f"Impossible de {action} : l'inventaire est {label}", code="statut_incompatible"
        )


def save_entries(db: Session, count_id: int, data: CountEntries) -> CountRead:
    count = _count(db, count_id, for_update=True)
    _open(count, "saisir")
    lines = {line.id: line for line in count.lines}
    for entry in data.entries:
        line = lines.get(entry.line_id)
        if line is None:
            raise NotFound(f"Ligne {entry.line_id} introuvable dans cet inventaire")
        line.counted_qty = entry.counted_qty
    count.updated_at = now()
    db.commit()
    return get_count(db, count.id)


def add_count_line(db: Session, count_id: int, data: CountLineAdd) -> CountRead:
    count = _count(db, count_id, for_update=True)
    _open(count, "ajouter une ligne")
    catalog.get_article(db, data.article_id)
    location = _location_of_site(db, data.location_id, count.site_id)
    if count.location_id is not None and location.id != count.location_id:
        raise Invalid("Cet inventaire ne porte que sur un emplacement")
    for line in count.lines:
        if (line.article_id, line.location_id, line.dot) == (
            data.article_id,
            location.id,
            data.dot,
        ):
            line.counted_qty = data.counted_qty  # déjà dans la liste : on met à jour
            break
    else:
        count.lines.append(
            CountLine(
                article_id=data.article_id,
                location_id=location.id,
                dot=data.dot,
                expected_qty=Decimal(0),
                counted_qty=data.counted_qty,
            )
        )
    count.updated_at = now()
    db.commit()
    return get_count(db, count.id)


def validate_count(
    db: Session, ctx: RequestContext, count_id: int, data: CountValidate
) -> CountRead:
    """Valide : chaque écart (compté − théorique) devient un mouvement « inventaire ».

    On applique l'ÉCART et non la quantité comptée : une réception arrivée entre
    l'ouverture et la validation reste donc bien en stock.
    """
    count = _count(db, count_id, for_update=True)
    _open(count, "valider")
    if data.version != count.version:
        raise Conflict(
            "L'inventaire a été modifié entre-temps, rechargez-le", code="modifie_entre_temps"
        )
    uncounted = [line for line in count.lines if line.counted_qty is None]
    if uncounted and not data.uncounted_as_zero:
        raise Invalid(
            f"{len(uncounted)} ligne(s) non comptée(s). Comptez-les, ou validez en les "
            "considérant à zéro."
        )
    locations = repo.locations_by_ids(db, {line.location_id for line in count.lines})
    for line in count.lines:
        if line.counted_qty is None:
            line.counted_qty = Decimal(0)
        difference = line.counted_qty - line.expected_qty
        if difference == 0:
            continue
        _move(
            db,
            _Move(
                kind="inventaire",
                article_id=line.article_id,
                location=locations[line.location_id],
                dot=line.dot,
                quantity=difference,
                source=f"count:{count.id}",
                reference=count.number,
            ),
        )
    count.status = "valide"
    count.validated_at = now()
    count.validated_by = ctx.user_id
    db.commit()
    return get_count(db, count.id)


def cancel_count(db: Session, count_id: int) -> CountRead:
    count = _count(db, count_id, for_update=True)
    _open(count, "annuler")
    count.status = "annule"
    db.commit()
    return get_count(db, count.id)


def _count_item(
    count: Count,
    sites: dict[int, SiteBrief],
    locations: dict[int, Location],
    line_count: int,
    counted: int,
) -> dict:
    location = locations.get(count.location_id) if count.location_id else None
    return dict(
        id=count.id,
        number=count.number,
        site=sites[count.site_id],
        location=LocationBrief(id=location.id, code=location.code) if location else None,
        status=count.status,
        note=count.note,
        line_count=line_count,
        counted_count=counted,
        created_at=count.created_at,
        validated_at=count.validated_at,
    )


def list_counts(
    db: Session, status: str | None, site_id: int | None, limit: int, offset: int
) -> CountPage:
    rows, total = repo.list_counts(db, status, site_id, limit, offset)
    locations = repo.locations_by_ids(db, {c.location_id for c, *_ in rows if c.location_id})
    sites = _sites(db)
    return CountPage(
        items=[CountListItem(**_count_item(c, sites, locations, n, k)) for c, n, k in rows],
        total=total,
    )


def get_count(db: Session, count_id: int) -> CountRead:
    count = _count(db, count_id)
    location_ids = {line.location_id for line in count.lines}
    if count.location_id:
        location_ids.add(count.location_id)
    locations = repo.locations_by_ids(db, location_ids)
    articles = catalog.article_briefs(db, [line.article_id for line in count.lines])
    costs = repo.costs_of(db, set(articles))
    lines = sorted(
        count.lines,
        key=lambda x: (
            locations[x.location_id].code,
            articles[x.article_id].designation,
            repo.dot_key(x.dot),
        ),
    )
    views, value = [], Decimal(0)
    for line in lines:
        difference = None if line.counted_qty is None else line.counted_qty - line.expected_qty
        if difference:
            value += difference * costs.get(line.article_id, Decimal(0))
        location = locations[line.location_id]
        views.append(
            CountLineView(
                id=line.id,
                article=articles[line.article_id],
                location=LocationBrief(id=location.id, code=location.code),
                dot=line.dot,
                expected_qty=line.expected_qty,
                counted_qty=line.counted_qty,
                difference=difference,
            )
        )
    counted = sum(1 for line in count.lines if line.counted_qty is not None)
    return CountRead(
        **_count_item(count, _sites(db), locations, len(count.lines), counted),
        version=count.version,
        lines=views,
        value_difference=value.quantize(CENT, rounding=ROUND_HALF_UP),
    )


# --- Réservations, disponible et sorties (appelés par le module ventes) ---------------


@dataclass
class Availability:
    on_hand: Decimal  # en stock
    reserved: Decimal  # promis aux clients
    available: Decimal  # en stock − promis (négatif = rupture)


def availability(
    db: Session, article_ids: set[int], site_id: int | None
) -> dict[int, Availability]:
    on_hand = repo.on_hand_by(db, article_ids, site_id)
    reserved = repo.reserved_by(db, article_ids, site_id)
    result = {}
    for article_id in article_ids:
        h = Decimal(on_hand.get(article_id, 0))
        r = Decimal(reserved.get(article_id, 0))
        result[article_id] = Availability(on_hand=h, reserved=r, available=h - r)
    return result


def set_reservation(
    db: Session,
    *,
    source: str,
    article_id: int,
    site_id: int,
    quantity: Decimal,
    reference: str | None = None,
) -> None:
    """Fixe la quantité réservée pour `source` (une ligne de commande) ; 0 = supprime.
    NE COMMITE PAS."""
    reservation = repo.get_reservation(db, source)
    if quantity <= 0:
        if reservation is not None:
            db.delete(reservation)
            db.flush()
        return
    if reservation is None:
        reservation = Reservation(source=source)
        db.add(reservation)
    reservation.article_id = article_id
    reservation.site_id = site_id
    reservation.quantity = quantity
    reservation.reference = reference
    db.flush()


def average_costs(db: Session, article_ids: set[int]) -> dict[int, Decimal]:
    """CMP des articles (0 si jamais entré en stock)."""
    costs = repo.costs_of(db, article_ids)
    return {a: costs.get(a, Decimal(0)) for a in article_ids}


def location_codes(db: Session, ids: set[int]) -> dict[int, str]:
    return {i: x.code for i, x in repo.locations_by_ids(db, ids).items()}


@dataclass
class IssuedLot:
    location_id: int
    location_code: str
    dot: str
    quantity: Decimal
    unit_cost: Decimal


def issue(
    db: Session,
    *,
    article_id: int,
    site_id: int,
    quantity: Decimal,
    location_id: int | None,
    dot: str | None,
    source: str,
    reference: str,
) -> list[IssuedLot]:
    """Sortie de stock d'une livraison : les DOT les plus anciens d'abord (sauf DOT ou
    emplacement imposé). NE COMMITE PAS. Refuse s'il n'y a pas assez de stock physique."""
    _lock_cost(db, article_id)  # même ordre de verrous que les autres mouvements
    levels = repo.site_levels_fifo(db, site_id, article_id, location_id, dot)
    available = sum((x.quantity for x in levels), Decimal(0))
    if available < quantity:
        article = catalog.article_brief(catalog.get_article(db, article_id))
        where = f" (DOT {dot})" if dot else ""
        raise InsufficientStock(
            f"Stock insuffisant pour {article.code}{where} : {_qty(available)} en stock "
            f"dans le dépôt, {_qty(quantity)} à livrer"
        )
    locations = repo.locations_by_ids(db, {x.location_id for x in levels})
    lots: list[IssuedLot] = []
    remaining = quantity
    for level in levels:
        if remaining <= 0:
            break
        take = min(level.quantity, remaining)
        remaining -= take
        location = locations[level.location_id]
        move = _move(
            db,
            _Move(
                kind="livraison",
                article_id=article_id,
                location=location,
                dot=level.dot,
                quantity=-take,
                source=source,
                reference=reference,
            ),
        )
        lots.append(IssuedLot(location.id, location.code, level.dot, take, move.unit_cost))
    return lots


# --- Lecture ---------------------------------------------------------------------------


def _sites(db: Session) -> dict[int, SiteBrief]:
    return {s.id: SiteBrief(id=s.id, code=s.code, name=s.name) for s in org.list_sites(db)}


def _moves_read(db: Session, moves: list[StockMove]) -> list[MoveRead]:
    sites = _sites(db)
    locations = repo.locations_by_ids(db, {m.location_id for m in moves})
    articles = catalog.article_briefs(db, [m.article_id for m in moves])
    return [
        MoveRead(
            id=m.id,
            moved_at=m.moved_at,
            kind=m.kind,
            article=articles[m.article_id],
            site=sites[m.site_id],
            location=LocationBrief(id=m.location_id, code=locations[m.location_id].code),
            dot=m.dot,
            quantity=m.quantity,
            unit_cost=m.unit_cost,
            source=m.source,
            reference=m.reference,
            reason=m.reason,
            note=m.note,
            created_by=m.created_by,
        )
        for m in moves
    ]


def stock(
    db: Session,
    *,
    site_id: int | None,
    location_id: int | None,
    q: str | None,
    kind: str | None,
    sort: str,
    descending: bool,
    limit: int,
    offset: int,
) -> StockPage:
    articles = catalog.article_ids_matching(q, kind) if (q or kind) else None
    rows, total, total_qty, total_value = repo.stock_page(
        db,
        site_id=site_id,
        location_id=location_id,
        articles=articles,
        sort=sort,
        descending=descending,
        limit=limit,
        offset=offset,
    )
    briefs = catalog.article_briefs(db, [r[0] for r in rows])
    reserved = repo.reserved_by(db, {r[0] for r in rows}, site_id)
    return StockPage(
        items=[
            StockRow(
                article=briefs[article_id],
                quantity=quantity,
                reserved=Decimal(reserved.get(article_id, 0)),
                available=quantity - Decimal(reserved.get(article_id, 0)),
                average_cost=cost,
                value=Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP),
                oldest_dot=oldest[2:] + oldest[:2] if oldest else None,
            )
            for article_id, quantity, cost, value, oldest in rows
        ],
        total=total,
        total_quantity=total_qty,
        total_value=total_value.quantize(CENT, rounding=ROUND_HALF_UP),
    )


def article_stock(db: Session, article_id: int) -> ArticleStock:
    article = catalog.article_brief(catalog.get_article(db, article_id))
    levels: list[StockLevel] = repo.levels_of_article(db, article_id)
    sites = _sites(db)
    locations = repo.locations_by_ids(db, {x.location_id for x in levels})
    levels.sort(
        key=lambda x: (sites[x.site_id].code, locations[x.location_id].code, repo.dot_key(x.dot))
    )
    quantity = sum((x.quantity for x in levels), Decimal(0))
    cost = repo.get_cost(db, article_id)
    reserved = repo.reserved_by_site(db, article_id)
    per_site: dict[int, Decimal] = {}
    for x in levels:
        per_site[x.site_id] = per_site.get(x.site_id, Decimal(0)) + x.quantity
    site_rows = [
        SiteAvailability(
            site=sites[site],
            quantity=per_site.get(site, Decimal(0)),
            reserved=Decimal(reserved.get(site, 0)),
            available=per_site.get(site, Decimal(0)) - Decimal(reserved.get(site, 0)),
        )
        for site in sorted(set(per_site) | set(reserved), key=lambda i: sites[i].code)
    ]
    moves, _ = repo.search_moves(
        db, article_id=article_id, site_id=None, kind=None, source=None, articles=None,
        limit=20, offset=0,
    )  # fmt: skip
    return ArticleStock(
        article=article,
        quantity=quantity,
        average_cost=cost,
        value=(quantity * cost).quantize(CENT, rounding=ROUND_HALF_UP),
        reserved=sum((r.reserved for r in site_rows), Decimal(0)),
        sites=site_rows,
        levels=[
            LevelRead(
                site=sites[x.site_id],
                location=LocationBrief(id=x.location_id, code=locations[x.location_id].code),
                dot=x.dot,
                quantity=x.quantity,
            )
            for x in levels
        ],
        moves=_moves_read(db, moves),
    )


def list_moves(
    db: Session,
    *,
    article_id: int | None,
    site_id: int | None,
    kind: str | None,
    q: str | None,
    limit: int,
    offset: int,
) -> MovePage:
    moves, total = repo.search_moves(
        db,
        article_id=article_id,
        site_id=site_id,
        kind=kind,
        source=None,
        articles=catalog.article_ids_matching(q) if q else None,
        limit=limit,
        offset=offset,
    )
    return MovePage(items=_moves_read(db, moves), total=total)
