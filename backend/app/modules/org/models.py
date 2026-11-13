"""Schéma PostgreSQL `org` : les sociétés (entités juridiques) et leur numérotation."""

from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, BusinessEntity, CompanyScopedMixin, IdMixin, TimestampMixin


class Company(Base, BusinessEntity):
    """Une entité juridique : son SIREN, sa TVA, sa banque, sa propre numérotation."""

    __tablename__ = "companies"
    __table_args__ = (
        CheckConstraint("siren ~ '^[0-9]{9}$'", name="siren_format"),
        CheckConstraint("country_code ~ '^[A-Z]{2}$'", name="country_code_format"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_format"),
        {"schema": "org"},
    )

    code: Mapped[str] = mapped_column(String(20), unique=True)  # ex. « HOLD », « FIL-NORD »
    name: Mapped[str] = mapped_column(String(200))  # raison sociale
    legal_form: Mapped[str | None] = mapped_column(String(50))  # SAS, SARL…
    siren: Mapped[str | None] = mapped_column(String(9), unique=True)
    vat_number: Mapped[str | None] = mapped_column(String(20))
    address_line1: Mapped[str | None] = mapped_column(String(200))
    address_line2: Mapped[str | None] = mapped_column(String(200))
    postal_code: Mapped[str | None] = mapped_column(String(10))
    city: Mapped[str | None] = mapped_column(String(100))
    country_code: Mapped[str] = mapped_column(String(2), server_default="FR")
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(30))
    iban: Mapped[str | None] = mapped_column(String(34))
    bic: Mapped[str | None] = mapped_column(String(11))
    currency: Mapped[str] = mapped_column(String(3), server_default="EUR")
    # Mentions légales obligatoires sur les factures (Code de commerce, art. L441-9).
    share_capital: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))  # capital social
    rcs: Mapped[str | None] = mapped_column(String(80))  # « RCS Lyon B 123 456 789 »
    late_penalty: Mapped[str | None] = mapped_column(String(200))  # taux des pénalités de retard
    early_payment_discount: Mapped[str | None] = mapped_column(String(200))  # escompte
    invoice_footer: Mapped[str | None] = mapped_column(Text)  # mentions complémentaires
    is_active: Mapped[bool] = mapped_column(server_default="true")


class NumberSequence(Base, IdMixin, TimestampMixin, CompanyScopedMixin):
    """Compteur de numérotation d'une société (factures, avoirs, commandes…).

    La loi impose une numérotation des factures continue et sans trou, PAR entité
    juridique : chaque société a donc ses propres compteurs. Protégé par la RLS.
    """

    __tablename__ = "number_sequences"
    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        CheckConstraint("padding BETWEEN 1 AND 12", name="padding_range"),
        CheckConstraint("next_value >= 1", name="next_value_positive"),
        {"schema": "org"},
    )

    code: Mapped[str] = mapped_column(String(30))  # « invoice », « credit_note »…
    label: Mapped[str] = mapped_column(String(100))
    prefix: Mapped[str] = mapped_column(String(30))  # « FA-{year}- » → FA-2026-00042
    padding: Mapped[int] = mapped_column(server_default="5")
    next_value: Mapped[int] = mapped_column(BigInteger, server_default="1")
    reset_yearly: Mapped[bool] = mapped_column(server_default="true")
    current_year: Mapped[int | None]


class Site(Base, BusinessEntity, CompanyScopedMixin):
    """Dépôt (entrepôt, magasin) d'une société : lieu de livraison des achats, et
    demain emplacement du stock."""

    __tablename__ = "sites"
    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        Index("uq_sites_gln", "gln", unique=True, postgresql_where=text("gln IS NOT NULL")),
        CheckConstraint("gln ~ '^[0-9]{13}$'", name="gln_format"),
        CheckConstraint("country_code ~ '^[A-Z]{2}$'", name="country_code_format"),
        {"schema": "org"},
    )

    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    address_line1: Mapped[str] = mapped_column(String(200))
    address_line2: Mapped[str | None] = mapped_column(String(200))
    postal_code: Mapped[str] = mapped_column(String(10))
    city: Mapped[str] = mapped_column(String(100))
    country_code: Mapped[str] = mapped_column(String(2), server_default="FR")
    phone: Mapped[str | None] = mapped_column(String(30))
    # Consignes pour le transporteur : horaires de réception, quai, accès poids lourds…
    delivery_notes: Mapped[str | None] = mapped_column(Text)
    gln: Mapped[str | None] = mapped_column(String(13))
    is_default: Mapped[bool] = mapped_column(server_default="false")
    is_active: Mapped[bool] = mapped_column(server_default="true")
