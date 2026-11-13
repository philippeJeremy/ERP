"""Schémas d'entrée / sortie du module facturation."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.shared.schemas import ReadSchema, Schema

PaymentMethod = Literal["virement", "prelevement", "cheque", "lcr", "carte", "especes"]
Money = Field(gt=0, max_digits=14, decimal_places=2)
Account = Field(min_length=1, max_length=20, pattern=r"^[0-9A-Z]+$")


# --- Réglages ---------------------------------------------------------------------------


class SettingsIn(Schema):
    default_payment_days: int = Field(30, ge=0, le=120)
    default_vat_rate: Decimal = Field(Decimal(20), ge=0, le=100, max_digits=5, decimal_places=2)
    customer_account: str = Account
    supplier_account: str = Account
    sales_goods_account: str = Account
    sales_services_account: str = Account
    eco_fee_account: str = Account
    vat_collected_account: str = Account
    purchases_account: str = Account
    vat_deductible_account: str = Account
    bank_account: str = Account
    cash_account: str = Account
    sales_journal: str = Field(min_length=1, max_length=5)
    purchases_journal: str = Field(min_length=1, max_length=5)
    bank_journal: str = Field(min_length=1, max_length=5)


class SettingsRead(ReadSchema):
    default_payment_days: int
    default_vat_rate: Decimal
    customer_account: str
    supplier_account: str
    sales_goods_account: str
    sales_services_account: str
    eco_fee_account: str
    vat_collected_account: str
    purchases_account: str
    vat_deductible_account: str
    bank_account: str
    cash_account: str
    sales_journal: str
    purchases_journal: str
    bank_journal: str


# --- À facturer -------------------------------------------------------------------------


class DeliveryToBill(Schema):
    id: int
    number: str
    delivered_on: date
    order_id: int
    order_number: str
    customer_reference: str | None
    total_ht: Decimal  # estimation au prix de la commande


class CustomerToBill(Schema):
    customer_id: int
    customer_code: str
    customer_name: str
    deliveries: list[DeliveryToBill]
    total_ht: Decimal


class FromDeliveries(Schema):
    delivery_ids: list[int] = Field(min_length=1, max_length=500)
    grouping: Literal["par_bl", "recap"] = "recap"  # une facture par BL, ou une par client
    issue: bool = False  # émettre tout de suite


# --- Factures ---------------------------------------------------------------------------


class InvoiceCreate(Schema):
    customer_id: int


class InvoiceUpdate(Schema):
    version: int
    customer_reference: str | None = Field(None, max_length=100)
    note: str | None = Field(None, max_length=2000)


class LineIn(Schema):
    """Ligne libre (prestation, frais) ou article, sur une facture en brouillon."""

    article_id: int | None = None
    designation: str = Field(min_length=1, max_length=250)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unit_price: Decimal = Field(ge=0, max_digits=14, decimal_places=4)
    discount_pct: Decimal = Field(Decimal(0), ge=0, le=100, max_digits=5, decimal_places=2)
    eco_fee: Decimal = Field(Decimal(0), ge=0, max_digits=10, decimal_places=4)
    vat_rate: Decimal | None = Field(None, ge=0, le=100, max_digits=5, decimal_places=2)


class InvoiceLineRead(ReadSchema):
    id: int
    line_no: int
    delivery_id: int | None
    delivery_number: str | None
    original_line_id: int | None
    article_id: int | None
    article_code: str | None
    designation: str
    quantity: Decimal
    unit_price: Decimal
    discount_pct: Decimal
    eco_fee: Decimal
    vat_rate: Decimal
    line_total: Decimal
    eco_total: Decimal = Decimal(0)
    creditable_qty: Decimal | None = None  # facture émise : quantité encore « avoirable »


class VatRow(Schema):
    rate: Decimal
    base: Decimal
    vat: Decimal


class AllocationRead(Schema):
    id: int
    amount: Decimal
    allocated_on: date
    source: Literal["reglement", "avoir"]
    source_id: int
    source_number: str
    invoice_id: int
    invoice_number: str | None


class DocRef(Schema):
    id: int
    number: str | None


class InvoiceRead(Schema):
    id: int
    number: str | None
    kind: str
    status: str
    customer_id: int
    customer_code: str
    customer_name: str
    customer_address: str | None
    customer_vat: str | None
    customer_siren: str | None
    customer_kind: str
    issue_date: date | None
    due_date: date | None
    delivery_date: date | None
    payment_terms: str | None
    customer_reference: str | None
    note: str | None
    total_ht: Decimal
    total_eco: Decimal
    total_vat: Decimal
    total_ttc: Decimal
    vat: list[VatRow]
    paid_amount: Decimal
    balance: Decimal  # facture : reste dû ; avoir : crédit encore disponible
    payment_status: Literal["brouillon", "a_payer", "partielle", "payee", "en_retard"]
    days_late: int
    original: DocRef | None
    credit_notes: list[DocRef]
    deliveries: list[DocRef]
    allocations: list[AllocationRead]
    reminder_count: int
    last_reminder_at: datetime | None
    issued_at: datetime | None
    lines: list[InvoiceLineRead]
    version: int
    created_at: datetime


class InvoiceListItem(Schema):
    id: int
    number: str | None
    kind: str
    status: str
    customer_id: int
    customer_name: str
    issue_date: date | None
    due_date: date | None
    total_ht: Decimal
    total_ttc: Decimal
    balance: Decimal
    payment_status: str
    days_late: int


class InvoicePage(Schema):
    items: list[InvoiceListItem]
    total: int
    total_ttc: Decimal
    total_balance: Decimal


class CreditLine(Schema):
    line_id: int
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)


class CreditNoteIn(Schema):
    full: bool = False  # tout annuler
    lines: list[CreditLine] = Field(default_factory=list)
    reason: str = Field(min_length=1, max_length=500)  # imprimé sur l'avoir


# --- Règlements -------------------------------------------------------------------------


class AllocationIn(Schema):
    invoice_id: int
    amount: Decimal = Money


class PaymentIn(Schema):
    customer_id: int
    paid_on: date
    amount: Decimal = Money
    method: PaymentMethod
    reference: str | None = Field(None, max_length=100)
    note: str | None = Field(None, max_length=1000)
    # Vide = lettrage automatique sur les factures les plus anciennes.
    allocations: list[AllocationIn] | None = None


class PaymentRead(Schema):
    id: int
    number: str
    customer_id: int
    customer_name: str
    paid_on: date
    amount: Decimal
    method: str
    reference: str | None
    note: str | None
    allocated: Decimal
    unallocated: Decimal
    allocations: list[AllocationRead]
    created_at: datetime


class PaymentPage(Schema):
    items: list[PaymentRead]
    total: int


class Allocate(Schema):
    allocations: list[AllocationIn] = Field(min_length=1, max_length=100)


class CustomerAccount(Schema):
    """Le compte d'un client : ce qu'il doit, ses crédits, ses retards."""

    customer_id: int
    customer_name: str
    invoices: list[InvoiceListItem]  # factures non soldées
    credit_notes: list[InvoiceListItem]  # avoirs avec un crédit disponible
    unallocated_payments: list[PaymentRead]
    total_due: Decimal
    overdue: Decimal
    available_credit: Decimal  # avoirs + règlements non lettrés
    uninvoiced: Decimal  # livré non facturé (TTC estimé)


class AgingRow(Schema):
    customer_id: int
    customer_name: str
    not_due: Decimal
    late_30: Decimal
    late_60: Decimal
    late_more: Decimal
    total: Decimal
    last_reminder_at: datetime | None


class Receivables(Schema):
    rows: list[AgingRow]
    totals: AgingRow


# --- Fournisseurs -----------------------------------------------------------------------


class ReceptionToBill(Schema):
    id: int
    number: str
    received_on: date
    delivery_note: str | None
    order_number: str
    total_ht: Decimal  # au prix net commandé
    line_count: int


class SupplierInvoiceCreate(Schema):
    partner_id: int
    supplier_number: str = Field(min_length=1, max_length=50)
    invoice_date: date
    due_date: date | None = None  # vide = d'après les conditions du fournisseur
    total_ht: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    total_vat: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    total_ttc: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    reception_ids: list[int] = Field(default_factory=list, max_length=200)
    note: str | None = Field(None, max_length=2000)


class SupplierInvoiceUpdate(Schema):
    version: int
    supplier_number: str | None = Field(None, min_length=1, max_length=50)
    invoice_date: date | None = None
    due_date: date | None = None
    total_ht: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=2)
    total_vat: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=2)
    total_ttc: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=2)
    note: str | None = Field(None, max_length=2000)


class SupplierLineIn(Schema):
    designation: str | None = Field(None, min_length=1, max_length=250)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unit_price: Decimal = Field(ge=0, max_digits=14, decimal_places=4)
    vat_rate: Decimal | None = Field(None, ge=0, le=100, max_digits=5, decimal_places=2)


class SupplierLineRead(Schema):
    id: int
    line_no: int
    reception_line_id: int | None
    reception_number: str | None
    order_number: str | None
    article_id: int | None
    designation: str
    quantity: Decimal
    unit_price: Decimal
    expected_quantity: Decimal | None
    expected_price: Decimal | None
    vat_rate: Decimal
    line_total: Decimal
    qty_gap: Decimal | None  # facturé − reçu
    price_gap: Decimal | None  # prix facturé − prix commandé


class SupplierPaymentIn(Schema):
    paid_on: date
    amount: Decimal = Money
    method: PaymentMethod
    reference: str | None = Field(None, max_length=100)


class SupplierPaymentRead(ReadSchema):
    id: int
    paid_on: date
    amount: Decimal
    method: str
    reference: str | None


class SupplierInvoiceRead(Schema):
    id: int
    number: str
    status: str
    partner_id: int
    partner_name: str
    supplier_number: str
    invoice_date: date
    due_date: date | None
    total_ht: Decimal
    total_vat: Decimal
    total_ttc: Decimal
    computed_ht: Decimal  # somme des lignes
    computed_vat: Decimal
    gaps: list[str]  # écarts constatés (quantités, prix, totaux)
    paid_amount: Decimal
    balance: Decimal
    note: str | None
    approved_at: datetime | None
    approval_note: str | None
    lines: list[SupplierLineRead]
    payments: list[SupplierPaymentRead]
    version: int
    created_at: datetime


class SupplierInvoiceListItem(Schema):
    id: int
    number: str
    status: str
    partner_id: int
    partner_name: str
    supplier_number: str
    invoice_date: date
    due_date: date | None
    total_ttc: Decimal
    balance: Decimal
    has_gaps: bool


class SupplierInvoicePage(Schema):
    items: list[SupplierInvoiceListItem]
    total: int


class Approve(Schema):
    version: int
    note: str | None = Field(None, max_length=500)  # obligatoire s'il y a des écarts


# --- Comptabilité -----------------------------------------------------------------------


class Entry(Schema):
    journal: str
    date: date
    piece: str
    account: str
    aux_account: str | None  # compte auxiliaire (code client / fournisseur)
    aux_label: str | None
    label: str
    debit: Decimal
    credit: Decimal


class EntriesPage(Schema):
    entries: list[Entry]
    total_debit: Decimal
    total_credit: Decimal
