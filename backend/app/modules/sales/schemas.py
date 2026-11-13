"""Schémas d'entrée / sortie du module ventes."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator

from app.modules.catalog.public import ArticleBrief
from app.shared.schemas import ReadSchema, Schema

QuoteStatus = Literal["brouillon", "envoye", "accepte", "refuse", "annule"]
OrderStatus = Literal["brouillon", "confirmee", "partielle", "livree", "cloturee", "annulee"]
DOT_PATTERN = r"^$|^(0[1-9]|[1-4][0-9]|5[0-3])[0-9]{2}$"


def _clean_dot(value: object) -> object:
    return value.replace(" ", "") if isinstance(value, str) else value


# --- Réglages et tarif ------------------------------------------------------------------


class SettingsIn(Schema):
    quote_validity_days: int = Field(30, ge=1, le=365)
    default_vat_rate: Decimal = Field(Decimal(20), ge=0, le=100, max_digits=5, decimal_places=2)
    quote_footer: str | None = Field(None, max_length=2000)
    delivery_footer: str | None = Field(None, max_length=2000)


class SettingsRead(ReadSchema):
    quote_validity_days: int
    default_vat_rate: Decimal
    quote_footer: str | None
    delivery_footer: str | None


class PriceIn(Schema):
    sale_price: Decimal = Field(ge=0, max_digits=14, decimal_places=4)
    eco_fee: Decimal = Field(Decimal(0), ge=0, max_digits=10, decimal_places=4)


class PriceRow(Schema):
    article: ArticleBrief
    kind: str
    sale_price: Decimal | None  # vide = pas encore de prix de vente
    eco_fee: Decimal
    average_cost: Decimal  # CMP du stock
    margin_pct: Decimal | None  # marge sur le prix public, au CMP
    updated_at: datetime | None


class PricePage(Schema):
    items: list[PriceRow]
    total: int


class Pricing(Schema):
    """Prix proposé pour un client et un article (aide à la saisie d'une ligne)."""

    article: ArticleBrief
    unit_price: Decimal | None
    discount_pct: Decimal
    eco_fee: Decimal
    vat_rate: Decimal
    net_price: Decimal | None  # prix remisé HT, hors éco
    on_hand: Decimal  # en stock dans le dépôt
    available: Decimal  # en stock − déjà promis
    average_cost: Decimal


# --- Lignes ------------------------------------------------------------------------------


class LineIn(Schema):
    article_id: int | None = None
    designation: str | None = Field(None, max_length=250)  # vide = celle de l'article
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    # Vides = tarif de vente, remise du client, éco-contribution du tarif, TVA par défaut.
    unit_price: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=4)
    discount_pct: Decimal | None = Field(None, ge=0, le=100, max_digits=5, decimal_places=2)
    eco_fee: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=4)
    vat_rate: Decimal | None = Field(None, ge=0, le=100, max_digits=5, decimal_places=2)
    dot: str = Field("", pattern=DOT_PATTERN)  # commande : DOT demandé par le client

    _dot = field_validator("dot", mode="before")(_clean_dot)


class LineRead(Schema):
    id: int
    line_no: int
    article: ArticleBrief | None
    designation: str
    quantity: Decimal
    unit_price: Decimal
    discount_pct: Decimal
    eco_fee: Decimal
    vat_rate: Decimal
    line_total: Decimal  # HT remisé, hors éco
    eco_total: Decimal
    unit_cost: Decimal | None  # CMP actuel (marge indicative)
    margin: Decimal | None


class OrderLineRead(LineRead):
    dot: str
    delivered_qty: Decimal
    remaining_qty: Decimal
    on_hand: Decimal | None  # en stock dans le dépôt (articles)


class VatRow(Schema):
    rate: Decimal
    base: Decimal
    vat: Decimal


class CustomerInfo(Schema):
    id: int
    code: str
    name: str
    kind: str
    payment_terms: str | None
    email: str | None
    phone: str | None
    vehicle_registration: str | None
    billing_address: list[str]
    delivery_address: list[str]


class SiteBrief(Schema):
    id: int
    code: str
    name: str


class DocRef(Schema):
    id: int
    number: str


class _DocRead(Schema):
    id: int
    number: str
    status: str
    customer: CustomerInfo
    site: SiteBrief
    customer_reference: str | None
    customer_note: str | None
    internal_note: str | None
    total_ht: Decimal
    total_eco: Decimal
    total_vat: Decimal
    total_ttc: Decimal
    vat: list[VatRow]
    margin: Decimal | None  # marge totale au CMP (articles seulement)
    version: int
    created_at: datetime
    updated_at: datetime


# --- Devis -------------------------------------------------------------------------------


class QuoteCreate(Schema):
    customer_id: int
    site_id: int | None = None  # vide = dépôt par défaut
    valid_until: date | None = None  # vide = date du jour + validité des réglages
    customer_reference: str | None = Field(None, max_length=50)
    customer_note: str | None = None
    internal_note: str | None = None


class QuoteUpdate(Schema):
    version: int
    site_id: int | None = None
    valid_until: date | None = None
    customer_reference: str | None = Field(None, max_length=50)
    customer_note: str | None = None
    internal_note: str | None = None


class QuoteRead(_DocRead):
    quote_date: date
    valid_until: date
    expired: bool
    sent_at: datetime | None
    decided_at: datetime | None
    refusal_reason: str | None
    order: DocRef | None
    lines: list[LineRead]


class QuoteListItem(Schema):
    id: int
    number: str
    status: str
    expired: bool
    customer_id: int
    customer_name: str
    quote_date: date
    valid_until: date
    total_ht: Decimal
    total_ttc: Decimal


class QuotePage(Schema):
    items: list[QuoteListItem]
    total: int


class Accept(Schema):
    version: int
    force: bool = False  # passer outre le dépassement d'encours


# --- Commandes et livraisons ------------------------------------------------------------


class OrderCreate(Schema):
    customer_id: int
    site_id: int | None = None
    requested_date: date | None = None
    customer_reference: str | None = Field(None, max_length=50)
    customer_note: str | None = None
    internal_note: str | None = None


class OrderUpdate(Schema):
    version: int
    site_id: int | None = None
    requested_date: date | None = None
    customer_reference: str | None = Field(None, max_length=50)
    customer_note: str | None = None
    internal_note: str | None = None


class DeliveryLineRead(Schema):
    order_line_id: int
    line_no: int
    designation: str
    quantity: Decimal
    location_code: str | None
    dot: str


class DeliveryRead(Schema):
    id: int
    number: str
    delivered_on: date
    carrier: str | None
    note: str | None
    lines: list[DeliveryLineRead]
    created_at: datetime


class Credit(Schema):
    limit: Decimal | None
    outstanding: Decimal  # commandes confirmées non soldées (TTC)


class OrderRead(_DocRead):
    order_date: date
    requested_date: date | None
    delivery_address: str | None
    confirmed_at: datetime | None
    closed_at: datetime | None
    cancel_reason: str | None
    quote: DocRef | None
    credit: Credit
    lines: list[OrderLineRead]
    deliveries: list[DeliveryRead]


class OrderListItem(Schema):
    id: int
    number: str
    status: str
    customer_id: int
    customer_name: str
    site_name: str
    order_date: date
    requested_date: date | None
    total_ht: Decimal
    total_ttc: Decimal


class OrderPage(Schema):
    items: list[OrderListItem]
    total: int


class Confirm(Schema):
    version: int
    force: bool = False


class DeliverLine(Schema):
    line_id: int
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    location_id: int | None = None  # vide = tout le dépôt
    dot: str | None = Field(None, pattern=DOT_PATTERN)  # vide = DOT de la ligne, ou FIFO

    _dot = field_validator("dot", mode="before")(_clean_dot)


class Deliver(Schema):
    delivered_on: date
    carrier: str | None = Field(None, max_length=100)
    note: str | None = Field(None, max_length=1000)
    lines: list[DeliverLine] = Field(min_length=1, max_length=500)


class Reason(Schema):
    reason: str = Field(min_length=1, max_length=500)


class CustomerActivity(Schema):
    credit: Credit
    quotes: list[QuoteListItem]
    orders: list[OrderListItem]
