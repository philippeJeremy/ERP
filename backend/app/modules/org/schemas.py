from pydantic import EmailStr, Field

from app.shared.schemas import ReadSchema, Schema


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
