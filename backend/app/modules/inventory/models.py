"""Schéma PostgreSQL `inventory` : le stock.

Principe : un JOURNAL de mouvements (`stock_moves`) qu'on ne modifie jamais. Une erreur
se corrige par un nouveau mouvement. La table `stock_levels` tient la somme à jour par
article × emplacement × DOT, pour lire le stock sans additionner tout le journal.

Valorisation au coût moyen pondéré (CMP), par société et par article (`article_costs`) :
recalculé à chaque entrée valorisée, les sorties partent au CMP du moment.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models import CURRENT_COMPANY_ID, Base, BusinessEntity, CompanyScopedMixin, IdMixin

MOVE_KINDS = (
    "reception",  # entrée d'une réception fournisseur
    "transfert",  # sortie (quantité négative) ou entrée (positive) d'un transfert
    "inventaire",  # écart constaté à la validation d'un inventaire
    "ajustement",  # casse, perte, correction… (avec motif)
    "livraison",  # sortie d'une livraison client
)
ADJUST_REASONS = ("casse", "perte", "vol", "erreur", "retour", "echantillon", "autre")
COUNT_STATUSES = ("en_cours", "valide", "annule")

# DOT : semaine (01-53) puis année sur 2 chiffres. Vide = article sans DOT.
DOT_CHECK = "dot = '' OR dot ~ '^(0[1-9]|[1-4][0-9]|5[0-3])[0-9]{2}$'"


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Location(Base, BusinessEntity, CompanyScopedMixin):
    """Emplacement dans un dépôt : allée-rack-niveau (A-03-2), quai, zone…"""

    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("site_id", "code"),
        # Un seul emplacement par défaut (le quai de réception) par dépôt.
        Index("uq_locations_default", "site_id", unique=True, postgresql_where=text("is_default")),
        {"schema": "inventory"},
    )

    site_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.sites.id"), index=True)
    code: Mapped[str] = mapped_column(String(30))
    name: Mapped[str | None] = mapped_column(String(100))
    is_default: Mapped[bool] = mapped_column(server_default="false")
    is_active: Mapped[bool] = mapped_column(server_default="true")


class StockLevel(Base, IdMixin, CompanyScopedMixin):
    """Quantité en stock d'un article, à un emplacement, pour un DOT."""

    __tablename__ = "stock_levels"
    __table_args__ = (
        UniqueConstraint("location_id", "article_id", "dot"),
        CheckConstraint(DOT_CHECK, name="dot_format"),
        CheckConstraint("quantity >= 0", name="quantity_positive"),  # jamais de stock négatif
        Index("ix_stock_levels_article", "company_id", "article_id"),
        {"schema": "inventory"},
    )

    article_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("catalog.articles.id"))
    site_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.sites.id"), index=True)
    location_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("inventory.locations.id"))
    dot: Mapped[str] = mapped_column(String(4), server_default="")
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), server_default="0")
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class ArticleCost(Base):
    """Coût moyen pondéré d'un article dans une société."""

    __tablename__ = "article_costs"
    __table_args__ = (
        CheckConstraint("average_cost >= 0", name="cost_positive"),
        {"schema": "inventory"},
    )

    company_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("org.companies.id"),
        primary_key=True,
        server_default=CURRENT_COMPANY_ID,
    )
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("catalog.articles.id"), primary_key=True
    )
    average_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4), server_default="0")
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Reservation(Base, IdMixin, CompanyScopedMixin):
    """Quantité promise à un client (ligne de commande non encore livrée), par dépôt.

    Disponible = stock du dépôt − réservations. Une réservation peut dépasser le stock :
    la commande est alors en rupture (« à commander »), mais le stock physique, lui,
    ne passe jamais en négatif.
    """

    __tablename__ = "reservations"
    __table_args__ = (
        UniqueConstraint("company_id", "source"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index("ix_reservations_article", "company_id", "article_id", "site_id"),
        {"schema": "inventory"},
    )

    article_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("catalog.articles.id"))
    site_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.sites.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    source: Mapped[str] = mapped_column(String(50))  # « sales_order_line:42 »
    reference: Mapped[str | None] = mapped_column(String(30))  # n° de la commande
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class StockMove(Base, IdMixin, CompanyScopedMixin):
    """Un mouvement du journal. Jamais modifié ni supprimé (droits retirés en base)."""

    __tablename__ = "stock_moves"
    __table_args__ = (
        CheckConstraint(_in("kind", MOVE_KINDS), name="kind"),
        CheckConstraint(DOT_CHECK, name="dot_format"),
        CheckConstraint("quantity <> 0", name="quantity_not_zero"),
        Index("ix_stock_moves_article", "company_id", "article_id", "moved_at"),
        {"schema": "inventory"},
    )

    moved_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    article_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("catalog.articles.id"))
    site_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.sites.id"))
    location_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("inventory.locations.id"))
    dot: Mapped[str] = mapped_column(String(4), server_default="")
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))  # + entrée, − sortie
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4))  # coût unitaire du mouvement
    # Pièce d'origine : « reception:12 », « transfer:3 », « count:5 »… et son numéro lisible.
    source: Mapped[str | None] = mapped_column(String(40), index=True)
    reference: Mapped[str | None] = mapped_column(String(50))
    reason: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("auth.users.id"),
        server_default=text("NULLIF(current_setting('app.user_id', true), '')::bigint"),
    )


class Transfer(Base, BusinessEntity, CompanyScopedMixin):
    """Transfert entre deux dépôts (immédiat : sortie et entrée au même moment)."""

    __tablename__ = "transfers"
    __table_args__ = (
        UniqueConstraint("company_id", "number"),
        CheckConstraint("from_site_id <> to_site_id", name="different_sites"),
        {"schema": "inventory"},
    )

    number: Mapped[str] = mapped_column(String(30))
    from_site_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.sites.id"))
    to_site_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.sites.id"))
    transferred_on: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)


class Count(Base, BusinessEntity, CompanyScopedMixin):
    """Inventaire (comptage) d'un dépôt, ou d'un seul emplacement."""

    __tablename__ = "counts"
    __table_args__ = (
        UniqueConstraint("company_id", "number"),
        CheckConstraint(_in("status", COUNT_STATUSES), name="status"),
        {"schema": "inventory"},
    )

    number: Mapped[str] = mapped_column(String(30))
    site_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.sites.id"))
    location_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("inventory.locations.id")
    )
    status: Mapped[str] = mapped_column(String(10), server_default="en_cours")
    note: Mapped[str | None] = mapped_column(Text)
    validated_at: Mapped[datetime | None]
    validated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("auth.users.id"))

    lines: Mapped[list["CountLine"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="CountLine.id"
    )


class CountLine(Base, IdMixin, CompanyScopedMixin):
    __tablename__ = "count_lines"
    __table_args__ = (
        UniqueConstraint("count_id", "location_id", "article_id", "dot"),
        CheckConstraint(DOT_CHECK, name="dot_format"),
        CheckConstraint("counted_qty >= 0", name="counted_positive"),
        {"schema": "inventory"},
    )

    count_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("inventory.counts.id", ondelete="CASCADE"), index=True
    )
    article_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("catalog.articles.id"))
    location_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("inventory.locations.id"))
    dot: Mapped[str] = mapped_column(String(4), server_default="")
    expected_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3))  # stock théorique à l'ouverture
    counted_qty: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))  # vide = pas encore compté
