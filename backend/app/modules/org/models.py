"""Schéma PostgreSQL `org` : les sociétés (entités juridiques) et leur numérotation."""

from sqlalchemy import BigInteger, CheckConstraint, String, UniqueConstraint
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
