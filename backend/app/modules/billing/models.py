"""Schéma PostgreSQL `billing` : factures et avoirs client, règlements, factures
fournisseur, réglages comptables.

Une facture émise ne se modifie ni ne se supprime jamais (obligation légale) : une
erreur se corrige par un AVOIR. La numérotation est continue, sans trou, par
société et par année (FA-2026-00001, AV-2026-00001), attribuée à l'émission :
un brouillon supprimé ne laisse pas de trou.

Lettrage : une `allocation` affecte tout ou partie d'un règlement (ou d'un avoir)
à une facture. Reste dû = TTC − affectations.
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

INVOICE_KINDS = ("facture", "avoir")
INVOICE_STATUSES = ("brouillon", "emise")
PAYMENT_METHODS = ("virement", "prelevement", "cheque", "lcr", "carte", "especes")
SUPPLIER_STATUSES = ("brouillon", "bon_a_payer", "annulee")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class BillingSettings(Base):
    """Réglages de la facturation et plan comptable simplifié, un par société."""

    __tablename__ = "settings"
    __table_args__ = {"schema": "billing"}

    company_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("org.companies.id"),
        primary_key=True,
        server_default=CURRENT_COMPANY_ID,
    )
    default_payment_days: Mapped[int] = mapped_column(server_default="30")
    default_vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), server_default="20")
    # Comptes comptables (plan comptable général).
    customer_account: Mapped[str] = mapped_column(String(20), server_default="411000")
    supplier_account: Mapped[str] = mapped_column(String(20), server_default="401000")
    sales_goods_account: Mapped[str] = mapped_column(String(20), server_default="707000")
    sales_services_account: Mapped[str] = mapped_column(String(20), server_default="706000")
    eco_fee_account: Mapped[str] = mapped_column(String(20), server_default="708500")
    vat_collected_account: Mapped[str] = mapped_column(String(20), server_default="445710")
    purchases_account: Mapped[str] = mapped_column(String(20), server_default="607000")
    vat_deductible_account: Mapped[str] = mapped_column(String(20), server_default="445660")
    bank_account: Mapped[str] = mapped_column(String(20), server_default="512000")
    cash_account: Mapped[str] = mapped_column(String(20), server_default="530000")
    sales_journal: Mapped[str] = mapped_column(String(5), server_default="VT")
    purchases_journal: Mapped[str] = mapped_column(String(5), server_default="AC")
    bank_journal: Mapped[str] = mapped_column(String(5), server_default="BQ")


class TotalsFields:
    total_ht: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")  # éco comprise
    total_eco: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    total_vat: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    total_ttc: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")


class Invoice(Base, BusinessEntity, CompanyScopedMixin, TotalsFields):
    """Facture ou avoir client. Les montants d'un avoir sont positifs (le type dit le sens)."""

    __tablename__ = "invoices"
    __table_args__ = (
        Index(
            "uq_invoices_company_number",
            "company_id",
            "number",
            unique=True,
            postgresql_where=text("number IS NOT NULL"),
        ),
        CheckConstraint(_in("kind", INVOICE_KINDS), name="kind"),
        CheckConstraint(_in("status", INVOICE_STATUSES), name="status"),
        CheckConstraint("paid_amount >= 0", name="paid_positive"),
        {"schema": "billing"},
    )

    number: Mapped[str | None] = mapped_column(String(30))  # attribué à l'émission
    kind: Mapped[str] = mapped_column(String(10), server_default="facture")
    status: Mapped[str] = mapped_column(String(10), server_default="brouillon", index=True)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("partners.partners.id"), index=True
    )
    issue_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    delivery_date: Mapped[date | None] = mapped_column(Date)  # date de la livraison (vente)
    # Le client tel qu'il était à l'émission (la fiche peut changer ensuite).
    customer_code: Mapped[str | None] = mapped_column(String(20))
    customer_name: Mapped[str | None] = mapped_column(String(250))
    customer_address: Mapped[str | None] = mapped_column(Text)
    customer_siren: Mapped[str | None] = mapped_column(String(14))
    customer_vat: Mapped[str | None] = mapped_column(String(20))
    customer_kind: Mapped[str | None] = mapped_column(String(12))
    payment_terms: Mapped[str | None] = mapped_column(String(200))
    customer_reference: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(Text)  # imprimée sur la facture
    original_id: Mapped[int | None] = mapped_column(  # avoir : la facture corrigée
        BigInteger, ForeignKey("billing.invoices.id")
    )
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    issued_at: Mapped[datetime | None]
    issued_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("auth.users.id"))
    reminder_count: Mapped[int] = mapped_column(server_default="0")
    last_reminder_at: Mapped[datetime | None]
    sent_at: Mapped[datetime | None]  # dernier envoi par mail

    lines: Mapped[list["InvoiceLine"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="InvoiceLine.line_no"
    )


class InvoiceLine(Base, IdMixin, CompanyScopedMixin):
    __tablename__ = "invoice_lines"
    __table_args__ = (
        UniqueConstraint("invoice_id", "line_no"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="price_positive"),
        CheckConstraint("discount_pct BETWEEN 0 AND 100", name="discount_range"),
        CheckConstraint("eco_fee >= 0", name="eco_fee_positive"),
        CheckConstraint("vat_rate BETWEEN 0 AND 100", name="vat_range"),
        {"schema": "billing"},
    )

    invoice_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("billing.invoices.id", ondelete="CASCADE"), index=True
    )
    line_no: Mapped[int]
    delivery_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sales.deliveries.id"))
    delivery_number: Mapped[str | None] = mapped_column(String(30))
    order_line_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sales.order_lines.id")
    )
    original_line_id: Mapped[int | None] = mapped_column(  # avoir : la ligne corrigée
        BigInteger, ForeignKey("billing.invoice_lines.id")
    )
    article_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("catalog.articles.id"))
    article_code: Mapped[str | None] = mapped_column(String(30))
    ean: Mapped[str | None] = mapped_column(String(14))
    designation: Mapped[str] = mapped_column(String(250))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    discount_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), server_default="0")
    eco_fee: Mapped[Decimal] = mapped_column(Numeric(10, 4), server_default="0")
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))  # HT remisé, hors éco


class InvoiceDelivery(Base, IdMixin, CompanyScopedMixin):
    """Un bon de livraison n'est facturé qu'une fois (contrainte d'unicité)."""

    __tablename__ = "invoice_deliveries"
    __table_args__ = (UniqueConstraint("company_id", "delivery_id"), {"schema": "billing"})

    invoice_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("billing.invoices.id", ondelete="CASCADE"), index=True
    )
    delivery_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sales.deliveries.id"))


class Payment(Base, BusinessEntity, CompanyScopedMixin):
    """Un encaissement client (virement reçu, chèque, carte…)."""

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("company_id", "number"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(_in("method", PAYMENT_METHODS), name="method"),
        {"schema": "billing"},
    )

    number: Mapped[str] = mapped_column(String(30))  # RG-2026-00001
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("partners.partners.id"), index=True
    )
    paid_on: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    method: Mapped[str] = mapped_column(String(20))
    reference: Mapped[str | None] = mapped_column(String(100))  # n° de chèque, libellé banque
    note: Mapped[str | None] = mapped_column(Text)


class Allocation(Base, IdMixin, CompanyScopedMixin):
    """Lettrage : tout ou partie d'un règlement OU d'un avoir affecté à une facture."""

    __tablename__ = "allocations"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("(payment_id IS NULL) <> (credit_note_id IS NULL)", name="one_source"),
        {"schema": "billing"},
    )

    invoice_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("billing.invoices.id"), index=True
    )
    payment_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("billing.payments.id", ondelete="CASCADE"), index=True
    )
    credit_note_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("billing.invoices.id"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    allocated_on: Mapped[date] = mapped_column(Date)


# --- Fournisseurs ---------------------------------------------------------------------


class SupplierInvoice(Base, BusinessEntity, CompanyScopedMixin):
    """Facture reçue d'un fournisseur, contrôlée contre les commandes et réceptions."""

    __tablename__ = "supplier_invoices"
    __table_args__ = (
        UniqueConstraint("company_id", "number"),
        # Un fournisseur ne numérote qu'une fois une facture : doublon = erreur de saisie.
        Index(
            "uq_supplier_invoices_ref",
            "company_id",
            "partner_id",
            "supplier_number",
            unique=True,
            postgresql_where=text("status <> 'annulee'"),
        ),
        CheckConstraint(_in("status", SUPPLIER_STATUSES), name="status"),
        CheckConstraint("paid_amount >= 0", name="paid_positive"),
        {"schema": "billing"},
    )

    number: Mapped[str] = mapped_column(String(30))  # FF-2026-00001 (n° interne)
    partner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("partners.partners.id"), index=True
    )
    supplier_number: Mapped[str] = mapped_column(String(50))  # n° de la facture reçue
    invoice_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(15), server_default="brouillon", index=True)
    # Montants imprimés sur la facture (saisis), comparés au calcul des lignes.
    total_ht: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    total_vat: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    total_ttc: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    note: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None]
    approved_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("auth.users.id"))
    approval_note: Mapped[str | None] = mapped_column(Text)  # validée malgré un écart : pourquoi

    lines: Mapped[list["SupplierInvoiceLine"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="SupplierInvoiceLine.line_no"
    )


class SupplierInvoiceLine(Base, IdMixin, CompanyScopedMixin):
    __tablename__ = "supplier_invoice_lines"
    __table_args__ = (
        UniqueConstraint("supplier_invoice_id", "line_no"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("vat_rate BETWEEN 0 AND 100", name="vat_range"),
        {"schema": "billing"},
    )

    supplier_invoice_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("billing.supplier_invoices.id", ondelete="CASCADE"), index=True
    )
    line_no: Mapped[int]
    reception_line_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("purchasing.reception_lines.id"), index=True
    )
    reception_number: Mapped[str | None] = mapped_column(String(30))
    order_number: Mapped[str | None] = mapped_column(String(30))
    article_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("catalog.articles.id"))
    designation: Mapped[str] = mapped_column(String(250))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))  # facturé
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 4))  # prix net facturé
    expected_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))  # reçu
    expected_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))  # prix net commandé
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))


class SupplierPayment(Base, BusinessEntity, CompanyScopedMixin):
    __tablename__ = "supplier_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(_in("method", PAYMENT_METHODS), name="method"),
        {"schema": "billing"},
    )

    supplier_invoice_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("billing.supplier_invoices.id"), index=True
    )
    paid_on: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    method: Mapped[str] = mapped_column(String(20))
    reference: Mapped[str | None] = mapped_column(String(100))
