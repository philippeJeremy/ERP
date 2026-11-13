"""Schéma PostgreSQL `purchasing` : commandes fournisseur et réceptions.

Cycle d'une commande (colonne `status`) :

    brouillon ──valider──► a_valider ──approuver──► validee ──envoyer──► envoyee
        ▲                     │ refuser                                    │ accusé
        └─────────────────────┘                                            ▼
                                       recue ◄── partielle ◄── réception ── confirmee
    annulee (tant que rien n'est reçu) · cloturee (reliquat abandonné)

Le numéro (CF-2026-00001) n'est attribué qu'à la validation : un brouillon supprimé
ne laisse pas de trou dans la numérotation.
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models import CURRENT_COMPANY_ID, Base, BusinessEntity, CompanyScopedMixin, IdMixin

STATUSES = (
    "brouillon", "a_valider", "validee", "envoyee", "confirmee",
    "partielle", "recue", "cloturee", "annulee",
)  # fmt: skip


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class PurchaseSettings(Base):
    """Réglages des achats, un par société."""

    __tablename__ = "settings"
    __table_args__ = (
        CheckConstraint("approval_threshold >= 0", name="threshold_positive"),
        {"schema": "purchasing"},
    )

    company_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("org.companies.id"),
        primary_key=True,
        server_default=CURRENT_COMPANY_ID,
    )
    # Au-delà de ce montant HT, une commande doit être validée par un « valideur ».
    # Vide = pas de validation.
    approval_threshold: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    # Mentions ajoutées en bas de chaque bon de commande.
    order_footer: Mapped[str | None] = mapped_column(Text)


class PurchaseOrder(Base, BusinessEntity, CompanyScopedMixin):
    __tablename__ = "orders"
    __table_args__ = (
        Index(
            "uq_orders_company_number",
            "company_id",
            "number",
            unique=True,
            postgresql_where=text("number IS NOT NULL"),
        ),
        CheckConstraint(_in("status", STATUSES), name="status"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_format"),
        {"schema": "purchasing"},
    )

    number: Mapped[str | None] = mapped_column(String(30))  # attribué à la validation
    status: Mapped[str] = mapped_column(String(20), server_default="brouillon", index=True)
    partner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("partners.partners.id"), index=True
    )
    site_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.sites.id"))  # livraison
    order_date: Mapped[date | None] = mapped_column(Date)  # date de validation
    expected_date: Mapped[date | None] = mapped_column(Date)  # livraison souhaitée
    currency: Mapped[str] = mapped_column(String(3), server_default="EUR")
    supplier_reference: Mapped[str | None] = mapped_column(String(50))  # n° chez le fournisseur
    supplier_note: Mapped[str | None] = mapped_column(Text)  # imprimé sur le bon de commande
    internal_note: Mapped[str | None] = mapped_column(Text)
    total_ht: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    submitted_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("auth.users.id"))
    submitted_at: Mapped[datetime | None]
    approved_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("auth.users.id"))
    approved_at: Mapped[datetime | None]
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None]
    confirmed_at: Mapped[datetime | None]
    closed_at: Mapped[datetime | None]
    cancel_reason: Mapped[str | None] = mapped_column(Text)

    lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="PurchaseOrderLine.line_no",
    )


class PurchaseOrderLine(Base, IdMixin, CompanyScopedMixin):
    __tablename__ = "order_lines"
    __table_args__ = (
        UniqueConstraint("order_id", "line_no"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="price_positive"),
        CheckConstraint("discount_pct BETWEEN 0 AND 100", name="discount_range"),
        CheckConstraint("received_qty >= 0", name="received_positive"),
        CheckConstraint("confirmed_qty >= 0", name="confirmed_positive"),
        {"schema": "purchasing"},
    )

    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("purchasing.orders.id", ondelete="CASCADE"), index=True
    )
    line_no: Mapped[int]
    # Article du catalogue (vide pour une ligne libre : port, emballage, prestation…).
    article_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("catalog.articles.id"), index=True
    )
    supplier_ref: Mapped[str | None] = mapped_column(String(50))
    designation: Mapped[str] = mapped_column(String(250))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    discount_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), server_default="0")
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    # Accusé du fournisseur : ce qu'il s'engage à livrer, et quand.
    confirmed_qty: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    confirmed_date: Mapped[date | None] = mapped_column(Date)
    received_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), server_default="0")


class Reception(Base, BusinessEntity, CompanyScopedMixin):
    """Une livraison reçue (avec son bon de livraison) : alimentera le stock."""

    __tablename__ = "receptions"
    __table_args__ = (UniqueConstraint("company_id", "number"), {"schema": "purchasing"})

    number: Mapped[str] = mapped_column(String(30))  # BR-2026-00001
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("purchasing.orders.id"), index=True
    )
    site_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("org.sites.id"))
    received_on: Mapped[date] = mapped_column(Date)
    delivery_note: Mapped[str | None] = mapped_column(String(50))  # n° du BL fournisseur
    note: Mapped[str | None] = mapped_column(Text)

    lines: Mapped[list["ReceptionLine"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class ReceptionLine(Base, IdMixin, CompanyScopedMixin):
    __tablename__ = "reception_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        {"schema": "purchasing"},
    )

    reception_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("purchasing.receptions.id", ondelete="CASCADE"), index=True
    )
    order_line_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("purchasing.order_lines.id"), index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
