"""Schéma PostgreSQL `sales` : tarif, devis, commandes client, livraisons.

    Devis : brouillon ──envoyer──► envoye ──accepter──► accepte (crée la commande)
                 ▲                    │ refuser
                 └──── rouvrir ───────┴──► refuse          annule à tout moment avant accord

    Commande : brouillon ──confirmer (réserve le stock)──► confirmee
               ──livraison──► partielle ──► livree
    annulee (rien de livré) · cloturee (reliquat abandonné)

Les montants sont en HT. L'éco-contribution des pneus (filière de recyclage) s'ajoute
au prix, sans remise, et entre dans la base de TVA.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from app.shared.models import CURRENT_COMPANY_ID, Base, BusinessEntity, CompanyScopedMixin, IdMixin

QUOTE_STATUSES = ("brouillon", "envoye", "accepte", "refuse", "annule")
ORDER_STATUSES = ("brouillon", "confirmee", "partielle", "livree", "cloturee", "annulee")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class SalesSettings(Base):
    __tablename__ = "settings"
    __table_args__ = (
        CheckConstraint("quote_validity_days BETWEEN 1 AND 365", name="validity_range"),
        CheckConstraint("default_vat_rate BETWEEN 0 AND 100", name="vat_range"),
        {"schema": "sales"},
    )

    company_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("org.companies.id"),
        primary_key=True,
        server_default=CURRENT_COMPANY_ID,
    )
    quote_validity_days: Mapped[int] = mapped_column(server_default="30")
    default_vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), server_default="20")
    quote_footer: Mapped[str | None] = mapped_column(Text)  # mentions en bas des devis
    delivery_footer: Mapped[str | None] = mapped_column(Text)  # mentions en bas des BL


class Price(Base, BusinessEntity, CompanyScopedMixin):
    """Prix de vente HT d'un article dans la société (le catalogue est commun au groupe,
    le tarif est propre à chaque société)."""

    __tablename__ = "prices"
    __table_args__ = (
        UniqueConstraint("company_id", "article_id"),
        CheckConstraint("sale_price >= 0", name="price_positive"),
        CheckConstraint("eco_fee >= 0", name="eco_fee_positive"),
        {"schema": "sales"},
    )

    article_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("catalog.articles.id"))
    sale_price: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    eco_fee: Mapped[Decimal] = mapped_column(Numeric(10, 4), server_default="0")


class LineFields:
    """Colonnes communes aux lignes de devis et de commande."""

    line_no: Mapped[int]

    @declared_attr
    def article_id(cls) -> Mapped[int | None]:
        # Vide pour une ligne libre : montage, équilibrage, port, prestation…
        return mapped_column(BigInteger, ForeignKey("catalog.articles.id"), index=True)

    designation: Mapped[str] = mapped_column(String(250))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 4))  # prix de base HT
    discount_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), server_default="0")
    eco_fee: Mapped[Decimal] = mapped_column(Numeric(10, 4), server_default="0")  # unitaire
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))  # HT remisé, hors éco


def _line_checks() -> tuple:
    return (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="price_positive"),
        CheckConstraint("discount_pct BETWEEN 0 AND 100", name="discount_range"),
        CheckConstraint("eco_fee >= 0", name="eco_fee_positive"),
        CheckConstraint("vat_rate BETWEEN 0 AND 100", name="vat_range"),
    )


class TotalsFields:
    total_ht: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")  # éco comprise
    total_eco: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    total_vat: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    total_ttc: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")


class Quote(Base, BusinessEntity, CompanyScopedMixin, TotalsFields):
    __tablename__ = "quotes"
    __table_args__ = (
        UniqueConstraint("company_id", "number"),
        CheckConstraint(_in("status", QUOTE_STATUSES), name="status"),
        {"schema": "sales"},
    )

    number: Mapped[str] = mapped_column(String(30))  # DV-2026-00001
    status: Mapped[str] = mapped_column(String(20), server_default="brouillon", index=True)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("partners.partners.id"), index=True
    )
    site_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.sites.id"))  # expédition
    quote_date: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date] = mapped_column(Date)
    customer_reference: Mapped[str | None] = mapped_column(String(50))
    customer_note: Mapped[str | None] = mapped_column(Text)  # imprimé sur le devis
    internal_note: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None]
    decided_at: Mapped[datetime | None]  # accepté ou refusé
    refusal_reason: Mapped[str | None] = mapped_column(Text)
    order_id: Mapped[int | None] = mapped_column(BigInteger)  # commande créée à l'accord

    lines: Mapped[list["QuoteLine"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="QuoteLine.line_no"
    )


class QuoteLine(Base, IdMixin, CompanyScopedMixin, LineFields):
    __tablename__ = "quote_lines"
    __table_args__ = (UniqueConstraint("quote_id", "line_no"), *_line_checks(), {"schema": "sales"})

    quote_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.quotes.id", ondelete="CASCADE"), index=True
    )


class SalesOrder(Base, BusinessEntity, CompanyScopedMixin, TotalsFields):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("company_id", "number"),
        CheckConstraint(_in("status", ORDER_STATUSES), name="status"),
        {"schema": "sales"},
    )

    number: Mapped[str] = mapped_column(String(30))  # CC-2026-00001
    status: Mapped[str] = mapped_column(String(20), server_default="brouillon", index=True)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("partners.partners.id"), index=True
    )
    site_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.sites.id"))
    quote_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sales.quotes.id"))
    order_date: Mapped[date] = mapped_column(Date)
    requested_date: Mapped[date | None] = mapped_column(Date)  # livraison souhaitée
    customer_reference: Mapped[str | None] = mapped_column(String(50))
    delivery_address: Mapped[str | None] = mapped_column(Text)  # figée à la confirmation
    customer_note: Mapped[str | None] = mapped_column(Text)
    internal_note: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None]
    closed_at: Mapped[datetime | None]
    cancel_reason: Mapped[str | None] = mapped_column(Text)

    lines: Mapped[list["SalesOrderLine"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="SalesOrderLine.line_no"
    )


class SalesOrderLine(Base, IdMixin, CompanyScopedMixin, LineFields):
    __tablename__ = "order_lines"
    __table_args__ = (
        UniqueConstraint("order_id", "line_no"),
        *_line_checks(),
        CheckConstraint("delivered_qty >= 0", name="delivered_positive"),
        {"schema": "sales"},
    )

    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.orders.id", ondelete="CASCADE"), index=True
    )
    # DOT demandé par le client (vide = les plus anciens d'abord).
    dot: Mapped[str] = mapped_column(String(4), server_default="")
    delivered_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), server_default="0")


class Delivery(Base, BusinessEntity, CompanyScopedMixin):
    """Un bon de livraison : ce qui est parti chez le client (sortie de stock)."""

    __tablename__ = "deliveries"
    __table_args__ = (UniqueConstraint("company_id", "number"), {"schema": "sales"})

    number: Mapped[str] = mapped_column(String(30))  # BL-2026-00001
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sales.orders.id"), index=True)
    site_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.sites.id"))
    delivered_on: Mapped[date] = mapped_column(Date)
    carrier: Mapped[str | None] = mapped_column(String(100))  # transporteur, « retrait comptoir »
    note: Mapped[str | None] = mapped_column(Text)

    lines: Mapped[list["DeliveryLine"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="DeliveryLine.id"
    )


class DeliveryLine(Base, IdMixin, CompanyScopedMixin):
    __tablename__ = "delivery_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        {"schema": "sales"},
    )

    delivery_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.deliveries.id", ondelete="CASCADE"), index=True
    )
    order_line_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.order_lines.id"), index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    # Lot sorti (un même article peut partir de plusieurs DOT / emplacements).
    location_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("inventory.locations.id")
    )
    dot: Mapped[str] = mapped_column(String(4), server_default="")
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))  # CMP à la sortie (marge)
