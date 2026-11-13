from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.shared.schemas import ReadSchema, Schema

Status = Literal[
    "brouillon", "a_valider", "validee", "envoyee", "confirmee",
    "partielle", "recue", "cloturee", "annulee",
]  # fmt: skip


class OrderCreate(Schema):
    partner_id: int
    site_id: int | None = None  # vide = dépôt par défaut
    expected_date: date | None = None
    supplier_note: str | None = None
    internal_note: str | None = None


class OrderUpdate(Schema):
    version: int
    site_id: int | None = None
    expected_date: date | None = None
    supplier_reference: str | None = Field(None, max_length=50)
    supplier_note: str | None = None
    internal_note: str | None = None


class LineIn(Schema):
    article_id: int | None = None
    designation: str | None = Field(None, max_length=250)  # vide = celle de l'article
    supplier_ref: str | None = Field(None, max_length=50)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    # Vide = prix du fournisseur dans le catalogue.
    unit_price: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=4)
    discount_pct: Decimal = Field(Decimal(0), ge=0, le=100, max_digits=5, decimal_places=2)


class LineRead(ReadSchema):
    id: int
    line_no: int
    article_id: int | None
    supplier_ref: str | None
    designation: str
    quantity: Decimal
    unit_price: Decimal
    discount_pct: Decimal
    line_total: Decimal
    confirmed_qty: Decimal | None
    confirmed_date: date | None
    received_qty: Decimal


class SupplierInfo(Schema):
    id: int
    code: str
    name: str
    payment_terms: str | None
    min_order_amount: Decimal | None
    free_shipping_amount: Decimal | None
    lead_time_days: int | None
    email: str | None
    phone: str | None
    order_address: list[str]


class SiteBrief(Schema):
    id: int
    code: str
    name: str
    city: str


class ReceptionLineRead(ReadSchema):
    order_line_id: int
    quantity: Decimal


class ReceptionRead(ReadSchema):
    id: int
    number: str
    received_on: date
    delivery_note: str | None
    note: str | None
    created_at: datetime
    lines: list[ReceptionLineRead]


class OrderRead(Schema):
    id: int
    number: str | None
    status: str
    supplier: SupplierInfo
    site: SiteBrief
    order_date: date | None
    expected_date: date | None
    currency: str
    supplier_reference: str | None
    supplier_note: str | None
    internal_note: str | None
    total_ht: Decimal
    submitted_at: datetime | None
    approved_at: datetime | None
    rejection_reason: str | None
    sent_at: datetime | None
    confirmed_at: datetime | None
    closed_at: datetime | None
    cancel_reason: str | None
    approval_threshold: Decimal | None  # seuil de la société, pour l'affichage
    lines: list[LineRead]
    receptions: list[ReceptionRead]
    warnings: list[str]  # minimum de commande, franco, article arrêté…
    version: int
    created_at: datetime
    updated_at: datetime


class OrderListItem(Schema):
    id: int
    number: str | None
    status: str
    partner_id: int
    partner_name: str
    site_name: str
    order_date: date | None
    expected_date: date | None
    total_ht: Decimal
    line_count: int
    received_ratio: float  # 0 à 1


class OrderPage(Schema):
    items: list[OrderListItem]
    total: int


class Reason(Schema):
    reason: str = Field(min_length=1, max_length=500)


class AckLine(Schema):
    line_id: int
    confirmed_qty: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=3)
    confirmed_date: date | None = None


class Acknowledge(Schema):
    supplier_reference: str | None = Field(None, max_length=50)
    lines: list[AckLine]


class ReceiveLine(Schema):
    line_id: int
    quantity: Decimal = Field(ge=0, max_digits=14, decimal_places=3)


class Receive(Schema):
    received_on: date
    delivery_note: str | None = Field(None, max_length=50)
    note: str | None = None
    lines: list[ReceiveLine]


class SettingsIn(Schema):
    approval_threshold: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=2)
    order_footer: str | None = Field(None, max_length=2000)


class SettingsRead(Schema):
    approval_threshold: Decimal | None
    order_footer: str | None
