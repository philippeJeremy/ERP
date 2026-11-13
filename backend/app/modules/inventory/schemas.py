"""Schémas d'entrée / sortie du module inventory."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator

from app.modules.catalog.public import ArticleBrief
from app.modules.inventory.models import ADJUST_REASONS
from app.shared.schemas import ReadSchema, Schema

# DOT : semaine 01-53 puis année sur 2 chiffres (« 2324 » = semaine 23 de 2024).
DOT_PATTERN = r"^$|^(0[1-9]|[1-4][0-9]|5[0-3])[0-9]{2}$"
Quantity = Decimal
AdjustReason = Literal[ADJUST_REASONS]  # type: ignore[valid-type]


def _clean_dot(value: str | None) -> str | None:
    return value.replace(" ", "").strip() if isinstance(value, str) else value


class DotMixin(Schema):
    dot: str = Field("", pattern=DOT_PATTERN, description="Semaine + année : 2324. Vide si aucun")

    _dot = field_validator("dot", mode="before")(_clean_dot)


# --- Emplacements ----------------------------------------------------------------------


class LocationIn(Schema):
    code: str = Field(min_length=1, max_length=30)
    name: str | None = Field(None, max_length=100)
    is_default: bool = False
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


class LocationRead(ReadSchema):
    id: int
    site_id: int
    code: str
    name: str | None
    is_default: bool
    is_active: bool
    version: int


class SiteBrief(Schema):
    id: int
    code: str
    name: str


class LocationBrief(Schema):
    id: int
    code: str


# --- État du stock ---------------------------------------------------------------------


class StockRow(Schema):
    """Une ligne de l'état du stock : un article, tous dépôts ou un dépôt."""

    article: ArticleBrief
    quantity: Decimal
    average_cost: Decimal
    value: Decimal
    oldest_dot: str | None  # le DOT le plus ancien en stock (à sortir en premier)


class StockPage(Schema):
    items: list[StockRow]
    total: int
    total_quantity: Decimal
    total_value: Decimal


class LevelRead(Schema):
    site: SiteBrief
    location: LocationBrief
    dot: str
    quantity: Decimal


class MoveRead(Schema):
    id: int
    moved_at: datetime
    kind: str
    article: ArticleBrief
    site: SiteBrief
    location: LocationBrief
    dot: str
    quantity: Decimal
    unit_cost: Decimal
    source: str | None
    reference: str | None
    reason: str | None
    note: str | None
    created_by: int | None


class MovePage(Schema):
    items: list[MoveRead]
    total: int


class ArticleStock(Schema):
    """Le stock d'un article : où il est, quels DOT, à quel coût."""

    article: ArticleBrief
    quantity: Decimal
    average_cost: Decimal
    value: Decimal
    levels: list[LevelRead]  # triés dépôt, emplacement, puis DOT du plus ancien au plus récent
    moves: list[MoveRead]  # les derniers mouvements


# --- Ajustement -------------------------------------------------------------------------


class AdjustIn(DotMixin):
    article_id: int
    location_id: int
    quantity: Decimal = Field(max_digits=14, decimal_places=3, description="+ entrée, − sortie")
    reason: AdjustReason
    note: str | None = Field(None, max_length=500)
    unit_cost: Decimal | None = Field(
        None, ge=0, max_digits=14, decimal_places=4, description="Entrée seulement : coût"
    )

    @field_validator("quantity")
    @classmethod
    def _not_zero(cls, value: Decimal) -> Decimal:
        if value == 0:
            raise ValueError("La quantité ne peut pas être nulle")
        return value


# --- Transferts -------------------------------------------------------------------------


class TransferLineIn(Schema):
    article_id: int
    from_location_id: int
    to_location_id: int | None = None  # vide = emplacement par défaut du dépôt d'arrivée
    dot: str | None = Field(
        None, pattern=DOT_PATTERN, description="Vide = les DOT les plus anciens d'abord"
    )
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)

    _dot = field_validator("dot", mode="before")(_clean_dot)


class TransferIn(Schema):
    from_site_id: int
    to_site_id: int
    transferred_on: date
    note: str | None = Field(None, max_length=500)
    lines: list[TransferLineIn] = Field(min_length=1, max_length=500)


class TransferListItem(Schema):
    id: int
    number: str
    from_site: SiteBrief
    to_site: SiteBrief
    transferred_on: date
    note: str | None
    line_count: int
    total_quantity: Decimal
    created_at: datetime


class TransferPage(Schema):
    items: list[TransferListItem]
    total: int


class TransferRead(TransferListItem):
    moves: list[MoveRead]


# --- Inventaires ------------------------------------------------------------------------


class CountCreate(Schema):
    site_id: int
    location_id: int | None = None  # vide = tout le dépôt
    note: str | None = Field(None, max_length=500)


class CountLineRead(ReadSchema):
    id: int
    article_id: int
    location_id: int
    dot: str
    expected_qty: Decimal
    counted_qty: Decimal | None


class CountLineView(Schema):
    id: int
    article: ArticleBrief
    location: LocationBrief
    dot: str
    expected_qty: Decimal
    counted_qty: Decimal | None
    difference: Decimal | None


class CountListItem(Schema):
    id: int
    number: str
    site: SiteBrief
    location: LocationBrief | None
    status: str
    note: str | None
    line_count: int
    counted_count: int
    created_at: datetime
    validated_at: datetime | None


class CountPage(Schema):
    items: list[CountListItem]
    total: int


class CountRead(CountListItem):
    version: int
    lines: list[CountLineView]
    value_difference: Decimal  # valeur de l'écart au CMP (positif = gain)


class CountEntry(Schema):
    line_id: int
    counted_qty: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=3)


class CountEntries(Schema):
    entries: list[CountEntry] = Field(min_length=1, max_length=2000)


class CountLineAdd(DotMixin):
    """Un article trouvé en rayon mais absent de la liste (stock théorique zéro)."""

    article_id: int
    location_id: int
    counted_qty: Decimal = Field(ge=0, max_digits=14, decimal_places=3)


class CountValidate(Schema):
    version: int
    uncounted_as_zero: bool = False  # sinon : refus s'il reste des lignes non comptées
