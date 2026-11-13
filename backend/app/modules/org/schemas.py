from decimal import Decimal

from pydantic import EmailStr, Field, field_validator

from app.shared.schemas import ReadSchema, Schema
from app.shared.validators import clean_gln


class CompanyBase(Schema):
    name: str = Field(min_length=1, max_length=200)
    legal_form: str | None = Field(None, max_length=50)
    siren: str | None = Field(None, pattern=r"^[0-9]{9}$")
    vat_number: str | None = Field(None, max_length=20)
    address_line1: str | None = Field(None, max_length=200)
    address_line2: str | None = Field(None, max_length=200)
    postal_code: str | None = Field(None, max_length=10)
    city: str | None = Field(None, max_length=100)
    country_code: str = Field("FR", pattern=r"^[A-Z]{2}$")
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    iban: str | None = Field(None, max_length=34)
    bic: str | None = Field(None, max_length=11)
    currency: str = Field("EUR", pattern=r"^[A-Z]{3}$")
    share_capital: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=2)
    rcs: str | None = Field(None, max_length=80)
    late_penalty: str | None = Field(None, max_length=200)
    early_payment_discount: str | None = Field(None, max_length=200)
    invoice_footer: str | None = Field(None, max_length=2000)


class CompanyCreate(CompanyBase):
    code: str = Field(min_length=1, max_length=20, pattern=r"^[A-Z0-9_-]+$")


class CompanyUpdate(Schema):
    """Modification partielle : seuls les champs envoyés sont modifiés.

    `version` est obligatoire : c'est la version que l'utilisateur avait à l'écran.
    """

    version: int
    name: str | None = Field(None, min_length=1, max_length=200)
    legal_form: str | None = Field(None, max_length=50)
    siren: str | None = Field(None, pattern=r"^[0-9]{9}$")
    vat_number: str | None = Field(None, max_length=20)
    address_line1: str | None = Field(None, max_length=200)
    address_line2: str | None = Field(None, max_length=200)
    postal_code: str | None = Field(None, max_length=10)
    city: str | None = Field(None, max_length=100)
    country_code: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    iban: str | None = Field(None, max_length=34)
    bic: str | None = Field(None, max_length=11)
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    share_capital: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=2)
    rcs: str | None = Field(None, max_length=80)
    late_penalty: str | None = Field(None, max_length=200)
    early_payment_discount: str | None = Field(None, max_length=200)
    invoice_footer: str | None = Field(None, max_length=2000)
    is_active: bool | None = None


class CompanyRead(ReadSchema):
    id: int
    code: str
    name: str
    legal_form: str | None
    siren: str | None
    vat_number: str | None
    address_line1: str | None
    address_line2: str | None
    postal_code: str | None
    city: str | None
    country_code: str
    email: str | None
    phone: str | None
    iban: str | None
    bic: str | None
    currency: str
    share_capital: Decimal | None
    rcs: str | None
    late_penalty: str | None
    early_payment_discount: str | None
    invoice_footer: str | None
    is_active: bool
    version: int


class SequenceRead(ReadSchema):
    id: int
    code: str
    label: str
    prefix: str
    padding: int
    next_value: int
    reset_yearly: bool
    current_year: int | None


class SequenceUpdate(Schema):
    label: str | None = Field(None, min_length=1, max_length=100)
    prefix: str | None = Field(None, max_length=30)
    padding: int | None = Field(None, ge=1, le=12)
    reset_yearly: bool | None = None


class CompanyBrief(ReadSchema):
    id: int
    code: str
    name: str
    is_active: bool


class RoleBrief(Schema):
    id: int
    code: str
    name: str


class UserCompanyAccess(Schema):
    """Accès d'un utilisateur à une société (écran « Accès aux sociétés »)."""

    company: CompanyBrief
    roles: list[RoleBrief]
    can_manage: bool
    grantable_role_ids: list[int]
    extra_permissions: list[str]
    grantable_permissions: list[str]


class SiteIn(Schema):
    code: str = Field(min_length=1, max_length=20, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    address_line1: str = Field(min_length=1, max_length=200)
    address_line2: str | None = Field(None, max_length=200)
    postal_code: str = Field(min_length=1, max_length=10)
    city: str = Field(min_length=1, max_length=100)
    country_code: str = Field("FR", pattern=r"^[A-Z]{2}$")
    phone: str | None = Field(None, max_length=30)
    delivery_notes: str | None = None
    gln: str | None = None
    is_default: bool = False
    is_active: bool = True

    @field_validator("gln", mode="before")
    @classmethod
    def check_gln(cls, v: str | None) -> str | None:
        return clean_gln(v)


class SiteRead(ReadSchema):
    id: int
    code: str
    name: str
    address_line1: str
    address_line2: str | None
    postal_code: str
    city: str
    country_code: str
    phone: str | None
    delivery_notes: str | None
    gln: str | None
    is_default: bool
    is_active: bool
    version: int
