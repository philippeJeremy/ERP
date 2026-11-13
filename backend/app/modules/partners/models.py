"""Schéma PostgreSQL `partners` : les tiers (fournisseurs, et plus tard clients).

Une seule table pour toutes les entreprises externes, avec des rôles
(`is_supplier`, `is_customer`) : une entreprise à la fois fournisseur et cliente
n'existe qu'une fois. Les fiches sont propres à chaque société (Row-Level Security).
"""

from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models import Base, BusinessEntity, CompanyScopedMixin

PAYMENT_METHODS = ("virement", "prelevement", "cheque", "lcr", "carte", "especes")
CUSTOMER_KINDS = ("pro", "particulier")
ADDRESS_KINDS = ("siege", "commande", "enlevement", "retour", "facturation", "livraison", "autre")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Partner(Base, BusinessEntity, CompanyScopedMixin):
    __tablename__ = "partners"
    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        # Un SIRET identifie un établissement : pas deux fiches pour le même, dans une société.
        Index(
            "uq_partners_company_id_siret",
            "company_id",
            "siret",
            unique=True,
            postgresql_where=text("siret IS NOT NULL"),
        ),
        CheckConstraint("siret ~ '^[0-9]{14}$'", name="siret_format"),
        CheckConstraint("gln ~ '^[0-9]{13}$'", name="gln_format"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_format"),
        CheckConstraint("is_supplier OR is_customer", name="has_role"),
        CheckConstraint(_in("payment_method", PAYMENT_METHODS), name="payment_method"),
        CheckConstraint("payment_days BETWEEN 0 AND 120", name="payment_days_range"),
        CheckConstraint("lead_time_days >= 0", name="lead_time_positive"),
        CheckConstraint("min_order_amount >= 0", name="min_order_positive"),
        CheckConstraint("free_shipping_amount >= 0", name="free_shipping_positive"),
        CheckConstraint("parent_id <> id", name="not_own_parent"),
        CheckConstraint(_in("customer_kind", CUSTOMER_KINDS), name="customer_kind"),
        CheckConstraint(
            _in("customer_payment_method", PAYMENT_METHODS), name="customer_payment_method"
        ),
        CheckConstraint(
            "customer_payment_days BETWEEN 0 AND 120", name="customer_payment_days_range"
        ),
        CheckConstraint("credit_limit >= 0", name="credit_limit_positive"),
        CheckConstraint(
            "discount_pct BETWEEN 0 AND 100 AND discount_tire_pct BETWEEN 0 AND 100 "
            "AND discount_part_pct BETWEEN 0 AND 100 AND discount_accessory_pct BETWEEN 0 AND 100",
            name="discounts_range",
        ),
        {"schema": "partners"},
    )

    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))  # raison sociale
    legal_form: Mapped[str | None] = mapped_column(String(50))
    siret: Mapped[str | None] = mapped_column(String(14))
    vat_number: Mapped[str | None] = mapped_column(String(20))
    # GLN : identifiant GS1 de l'entreprise, utilisé dans les échanges EDI.
    gln: Mapped[str | None] = mapped_column(String(13))
    is_supplier: Mapped[bool] = mapped_column(server_default="false")
    is_customer: Mapped[bool] = mapped_column(server_default="false")
    # Groupement : la centrale d'achat, la maison mère…
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("partners.partners.id", ondelete="SET NULL"), index=True
    )
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(30))
    website: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(server_default="true")

    # --- Conditions d'achat (rôle fournisseur) ---
    supplier_account: Mapped[str | None] = mapped_column(String(20))  # compte comptable 401…
    payment_method: Mapped[str | None] = mapped_column(String(20))
    payment_days: Mapped[int | None]  # délai de paiement en jours
    payment_end_of_month: Mapped[bool] = mapped_column(server_default="false")  # « fin de mois »
    currency: Mapped[str] = mapped_column(String(3), server_default="EUR")
    lead_time_days: Mapped[int | None]  # délai de livraison habituel
    min_order_amount: Mapped[Decimal | None]  # minimum de commande
    free_shipping_amount: Mapped[Decimal | None]  # franco de port : livraison offerte au-delà

    # --- Conditions de vente (rôle client) ---
    customer_kind: Mapped[str | None] = mapped_column(String(12))  # pro / particulier
    first_name: Mapped[str | None] = mapped_column(String(100))  # particulier (nom dans `name`)
    vehicle_registration: Mapped[str | None] = mapped_column(String(15))  # immatriculation
    customer_account: Mapped[str | None] = mapped_column(String(20))  # compte comptable 411…
    customer_payment_method: Mapped[str | None] = mapped_column(String(20))
    customer_payment_days: Mapped[int | None]
    customer_payment_end_of_month: Mapped[bool] = mapped_column(server_default="false")
    credit_limit: Mapped[Decimal | None]  # encours autorisé
    # Remise générale, et remises par famille d'articles (vide = la générale s'applique).
    discount_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), server_default="0")
    discount_tire_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    discount_part_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    discount_accessory_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    # --- Banque ---
    bank_name: Mapped[str | None] = mapped_column(String(100))
    iban: Mapped[str | None] = mapped_column(String(34))
    bic: Mapped[str | None] = mapped_column(String(11))

    addresses: Mapped[list["PartnerAddress"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="(PartnerAddress.kind, PartnerAddress.is_primary.desc(), PartnerAddress.id)",
    )
    contacts: Mapped[list["PartnerContact"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="(PartnerContact.is_primary.desc(), PartnerContact.last_name)",
    )
    parent: Mapped["Partner | None"] = relationship(remote_side="Partner.id", lazy="joined")


class PartnerAddress(Base, BusinessEntity, CompanyScopedMixin):
    __tablename__ = "addresses"
    __table_args__ = (
        CheckConstraint(_in("kind", ADDRESS_KINDS), name="kind"),
        CheckConstraint("country_code ~ '^[A-Z]{2}$'", name="country_code_format"),
        CheckConstraint("gln ~ '^[0-9]{13}$'", name="gln_format"),
        {"schema": "partners"},
    )

    partner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("partners.partners.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    label: Mapped[str | None] = mapped_column(String(100))  # « Entrepôt de Lyon »
    line1: Mapped[str] = mapped_column(String(200))
    line2: Mapped[str | None] = mapped_column(String(200))
    postal_code: Mapped[str] = mapped_column(String(10))
    city: Mapped[str] = mapped_column(String(100))
    country_code: Mapped[str] = mapped_column(String(2), server_default="FR")
    gln: Mapped[str | None] = mapped_column(String(13))  # GLN du lieu (EDI)
    # Adresse par défaut pour son type (la commande part à l'adresse « commande » principale).
    is_primary: Mapped[bool] = mapped_column(server_default="false")


class PartnerContact(Base, BusinessEntity, CompanyScopedMixin):
    __tablename__ = "contacts"
    __table_args__ = {"schema": "partners"}

    partner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("partners.partners.id", ondelete="CASCADE"), index=True
    )
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    job_title: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(30))
    mobile: Mapped[str | None] = mapped_column(String(30))
    notes: Mapped[str | None] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(server_default="false")  # interlocuteur principal
