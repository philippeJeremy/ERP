from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.modules.catalog.tires import gtin_is_valid, size_label
from app.shared.schemas import ReadSchema, Schema

Kind = Literal["pneu", "piece", "accessoire"]
VehicleType = Literal[
    "tourisme", "4x4", "utilitaire", "moto", "poids_lourd", "agricole", "genie_civil", "autre"
]
Season = Literal["ete", "hiver", "4_saisons"]
LabelClass = Literal["A", "B", "C", "D", "E"]
NoiseClass = Literal["A", "B", "C"]


def _clean_ean(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.replace(" ", "")
    if not v:
        return None
    if not gtin_is_valid(v):
        raise ValueError("Code EAN invalide (8, 12, 13 ou 14 chiffres, clé de contrôle fausse ?)")
    return v


# --- Articles ----------------------------------------------------------------------


class TireSpecIn(Schema):
    vehicle_type: VehicleType = "tourisme"
    season: Season | None = None
    width: Decimal | None = Field(None, gt=0, max_digits=5, decimal_places=2)
    aspect_ratio: int | None = Field(None, ge=10, le=150)
    construction: Literal["R", "ZR", "D", "B", "-"] | None = "R"
    rim: Decimal | None = Field(None, gt=0, max_digits=4, decimal_places=1)
    load_index: str | None = Field(None, max_length=10, pattern=r"^\d{1,3}(/\d{1,3})?$")
    speed_index: str | None = Field(None, max_length=3, pattern=r"^[A-Z]\d?$")
    reinforced: bool = False
    runflat: bool = False
    studded: bool = False
    three_pmsf: bool = False
    mud_snow: bool = False
    fuel_class: LabelClass | None = None
    wet_class: LabelClass | None = None
    noise_db: int | None = Field(None, ge=50, le=90)
    noise_class: NoiseClass | None = None
    eprel_id: str | None = Field(None, max_length=20)


class TireSpecRead(ReadSchema):
    vehicle_type: str
    season: str | None
    width: Decimal | None
    aspect_ratio: int | None
    construction: str | None
    rim: Decimal | None
    load_index: str | None
    speed_index: str | None
    size_code: str | None
    reinforced: bool
    runflat: bool
    studded: bool
    three_pmsf: bool
    mud_snow: bool
    fuel_class: str | None
    wet_class: str | None
    noise_db: int | None
    noise_class: str | None
    eprel_id: str | None
    size: str | None = None

    @model_validator(mode="after")
    def compute_size(self):
        self.size = size_label(self.model_dump())
        return self


class _ArticleFields(Schema):
    ean: str | None = None
    brand: str | None = Field(None, max_length=100)  # nom de la marque (créée si nouvelle)
    manufacturer_ref: str | None = Field(None, max_length=50)
    category: str | None = Field(None, max_length=100)
    unit: str | None = Field(None, max_length=10)
    notes: str | None = None

    @field_validator("ean", mode="before")
    @classmethod
    def check_ean(cls, v: str | None) -> str | None:
        return _clean_ean(v)


class ArticleCreate(_ArticleFields):
    kind: Kind
    # Pneu sans désignation : construite à partir de la marque et de la dimension.
    designation: str | None = Field(None, max_length=250)
    tire: TireSpecIn | None = None

    @model_validator(mode="after")
    def check_kind(self):
        if self.kind == "pneu" and self.tire is None:
            self.tire = TireSpecIn()
        if self.kind != "pneu":
            self.tire = None
            if not self.designation:
                raise ValueError("La désignation est obligatoire")
        return self


class ArticleUpdate(_ArticleFields):
    version: int
    designation: str | None = Field(None, min_length=1, max_length=250)
    is_active: bool | None = None
    tire: TireSpecIn | None = None


class BrandRead(ReadSchema):
    id: int
    name: str


class ArticleRead(ReadSchema):
    id: int
    code: str
    kind: str
    ean: str | None
    brand: BrandRead | None
    manufacturer_ref: str | None
    designation: str
    category: str | None
    unit: str
    notes: str | None
    is_active: bool
    tire: TireSpecRead | None
    version: int
    created_at: datetime
    updated_at: datetime


class ArticleListItem(Schema):
    id: int
    code: str
    kind: str
    ean: str | None
    brand: str | None
    designation: str
    size: str | None
    season: str | None
    vehicle_type: str | None
    fuel_class: str | None
    wet_class: str | None
    noise_db: int | None
    is_active: bool
    supplier_count: int  # fournisseurs actifs dans la société courante
    best_price: Decimal | None  # meilleur prix d'achat actif dans la société courante


class ArticlePage(Schema):
    items: list[ArticleListItem]
    total: int


# --- Fournisseurs d'un article (par société) ------------------------------------------


class ArticleSupplierIn(Schema):
    partner_id: int
    supplier_ref: str | None = Field(None, max_length=50)
    purchase_price: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=4)
    currency: str = Field("EUR", pattern=r"^[A-Z]{3}$")
    is_preferred: bool = False


class ArticleSupplierUpdate(Schema):
    version: int
    supplier_ref: str | None = Field(None, max_length=50)
    purchase_price: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=4)
    is_preferred: bool | None = None
    is_discontinued: bool | None = None


class PartnerBrief(Schema):
    id: int
    code: str
    name: str


class ArticleBrief(Schema):
    id: int
    code: str
    designation: str
    ean: str | None
    brand: str | None
    size: str | None


class ArticleSupplierRead(Schema):
    id: int
    article: ArticleBrief
    partner: PartnerBrief
    supplier_ref: str | None
    purchase_price: Decimal | None
    currency: str
    is_preferred: bool
    is_discontinued: bool
    discontinued_at: datetime | None
    price_updated_at: datetime | None
    version: int


class ArticleSupplierPage(Schema):
    items: list[ArticleSupplierRead]
    total: int


# --- Imports -----------------------------------------------------------------------

MappingField = Literal[
    "ean", "supplier_ref", "manufacturer_ref", "brand", "designation", "purchase_price",
    "kind", "category", "vehicle_type", "season", "width", "aspect_ratio", "rim",
    "load_index", "speed_index", "fuel_class", "wet_class", "noise_db", "noise_class",
    "eprel_id",
]  # fmt: skip


class ImportProfileIn(Schema):
    partner_id: int
    name: str = Field("Tarif", min_length=1, max_length=100)
    file_format: Literal["csv", "excel"]
    delimiter: str | None = Field(None, max_length=1)
    encoding: Literal["utf-8-sig", "cp1252"] | None = None
    sheet_name: str | None = Field(None, max_length=100)
    header_row: int = Field(1, ge=1, le=50)
    mapping: dict[MappingField, str]
    full_catalog: bool = True
    default_kind: Kind = "pneu"
    default_vehicle_type: VehicleType | None = None
    parse_designation: bool = True

    @model_validator(mode="after")
    def check_mapping(self):
        if "purchase_price" not in self.mapping:
            raise ValueError("Indiquez la colonne du prix d'achat")
        if "ean" not in self.mapping and "supplier_ref" not in self.mapping:
            raise ValueError("Indiquez la colonne du code EAN ou de la référence fournisseur")
        return self


class ImportProfileRead(ReadSchema):
    id: int
    partner_id: int
    name: str
    file_format: str
    delimiter: str | None
    encoding: str | None
    sheet_name: str | None
    header_row: int
    mapping: dict[str, str]
    full_catalog: bool
    default_kind: str
    default_vehicle_type: str | None
    parse_designation: bool
    version: int
    updated_at: datetime


class FilePreview(Schema):
    file_format: str
    delimiter: str | None = None
    encoding: str | None = None
    sheets: list[str] | None = None
    sheet_name: str | None = None
    headers: list[str]
    rows: list[list[str]]
    suggested_mapping: dict[str, str]
    fields: dict[str, str]  # champs ERP disponibles et leur libellé


class ImportRunRead(ReadSchema):
    id: int
    partner_id: int
    partner_name: str | None = None
    profile_id: int | None
    source: str
    filename: str
    file_size: int
    status: str
    full_catalog: bool
    total_lines: int
    new_count: int
    updated_count: int
    unchanged_count: int
    reactivated_count: int
    discontinued_count: int
    error_count: int
    active_before: int
    message: str | None
    needs_confirmation: bool = False
    created_at: datetime
    analyzed_at: datetime | None
    applied_at: datetime | None


class ImportRunPage(Schema):
    items: list[ImportRunRead]
    total: int


class ImportLineRead(ReadSchema):
    id: int
    line_no: int | None
    status: str
    article_id: int | None
    data: dict
    old_price: Decimal | None
    new_price: Decimal | None
    error: str | None


class ImportLinePage(Schema):
    items: list[ImportLineRead]
    total: int


class ApplyImport(Schema):
    confirm_discontinue: bool = False


# --- Relèves automatiques (FTP / FTPS / SFTP) ---------------------------------------

DEFAULT_PORTS = {"sftp": 22, "ftps": 21, "ftp": 21}


class _SourceConnection(Schema):
    protocol: Literal["sftp", "ftps", "ftp"]
    # Nom ou adresse du serveur seulement (pas « sftp:// », pas de chemin).
    host: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9.\-:\[\]]+$")
    port: int | None = Field(None, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=100)
    auth_method: Literal["password", "key"] = "password"
    # Vide en modification = garder le secret enregistré.
    secret: str | None = Field(None, max_length=10_000)
    host_key: str | None = Field(None, max_length=200)
    tls_verify: bool = True
    remote_dir: str = Field("/", max_length=255)
    pattern: str = Field("*", min_length=1, max_length=100, pattern=r"^[^/\\]+$")

    @model_validator(mode="after")
    def defaults(self):
        if self.port is None:
            self.port = DEFAULT_PORTS[self.protocol]
        if self.protocol != "sftp":
            self.auth_method = "password"
            self.host_key = None
        return self


class ConnectionTestIn(_SourceConnection):
    source_id: int | None = None  # pour réutiliser le mot de passe déjà enregistré


class RemoteFileRead(Schema):
    name: str
    size: int
    mtime: datetime | None
    already_seen: bool = False


class ConnectionTestResult(Schema):
    host_key: str | None  # SFTP : empreinte à faire confirmer
    host_key_changed: bool = False
    files: list[RemoteFileRead]  # fichiers correspondant au motif, du plus récent au plus ancien


class ImportSourceIn(_SourceConnection):
    partner_id: int
    profile_id: int
    name: str = Field("Relève", min_length=1, max_length=100)
    interval_hours: int = Field(24, ge=1, le=168)
    auto_apply: bool = False
    is_active: bool = True


class ImportSourceRead(ReadSchema):
    id: int
    partner_id: int
    partner_name: str | None = None
    profile_id: int | None
    profile_name: str | None = None
    name: str
    protocol: str
    host: str
    port: int
    username: str
    auth_method: str
    has_secret: bool = False
    host_key: str | None
    tls_verify: bool
    remote_dir: str
    pattern: str
    interval_hours: int
    auto_apply: bool
    is_active: bool
    next_check_at: datetime | None
    last_check_at: datetime | None
    last_status: str | None
    last_message: str | None
    last_run_id: int | None
    version: int
