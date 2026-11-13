from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import EmailStr, Field, field_validator

from app.shared.schemas import ReadSchema, Schema

PaymentMethod = Literal["virement", "prelevement", "cheque", "lcr", "carte", "especes"]
AddressKind = Literal[
    "siege", "commande", "enlevement", "retour", "facturation", "livraison", "autre"
]


def _compact(value: str | None) -> str | None:
    """Retire espaces et points (« 552 100 554 00017 » → « 55210055400017 ») ; vide → None."""
    if value is None:
        return None
    value = value.replace(" ", "").replace(".", "").upper()
    return value or None


def iban_is_valid(iban: str) -> bool:
    """Clé de contrôle IBAN (norme ISO 13616, « modulo 97 ») : détecte les fautes de frappe."""
    if not (15 <= len(iban) <= 34) or not iban[:2].isalpha() or not iban[2:4].isdigit():
        return False
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(c, 36)) for c in rearranged)  # A=10, B=11… Z=35
    return digits.isdigit() and int(digits) % 97 == 1


class _PartnerFields(Schema):
    """Champs communs à la création et à la modification (tous facultatifs ici)."""

    legal_form: str | None = Field(None, max_length=50)
    siret: str | None = None
    vat_number: str | None = Field(None, max_length=20)
    parent_id: int | None = None
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    website: str | None = Field(None, max_length=200)
    notes: str | None = None
    supplier_account: str | None = Field(None, max_length=20)
    payment_method: PaymentMethod | None = None
    payment_days: int | None = Field(None, ge=0, le=120)
    lead_time_days: int | None = Field(None, ge=0, le=365)
    min_order_amount: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=2)
    free_shipping_amount: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=2)
    bank_name: str | None = Field(None, max_length=100)
    iban: str | None = None
    bic: str | None = None

    @field_validator("siret", "vat_number", "iban", "bic", mode="before")
    @classmethod
    def compact(cls, v: str | None) -> str | None:
        return _compact(v)

    @field_validator("siret")
    @classmethod
    def check_siret(cls, v: str | None) -> str | None:
        if v is not None and (len(v) != 14 or not v.isdigit()):
            raise ValueError("Le SIRET compte 14 chiffres")
        return v

    @field_validator("iban")
    @classmethod
    def check_iban(cls, v: str | None) -> str | None:
        if v is not None and not iban_is_valid(v):
            raise ValueError(
                "IBAN invalide (vérifiez les caractères : la clé de contrôle ne correspond pas)"
            )
        return v

    @field_validator("bic")
    @classmethod
    def check_bic(cls, v: str | None) -> str | None:
        if v is not None and not (len(v) in (8, 11) and v[:6].isalpha() and v.isalnum()):
            raise ValueError("Le BIC compte 8 ou 11 caractères (ex. BNPAFRPPXXX)")
        return v


class PartnerCreate(_PartnerFields):
    # Vide : un code est attribué automatiquement (T00001, T00002…).
    code: str | None = Field(None, max_length=20, pattern=r"^[A-Z0-9_-]*$")
    name: str = Field(min_length=1, max_length=200)
    is_supplier: bool = True
    is_customer: bool = False
    payment_end_of_month: bool = False
    currency: str = Field("EUR", pattern=r"^[A-Z]{3}$")


class PartnerUpdate(_PartnerFields):
    version: int
    name: str | None = Field(None, min_length=1, max_length=200)
    is_supplier: bool | None = None
    is_customer: bool | None = None
    is_active: bool | None = None
    payment_end_of_month: bool | None = None
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")


class PartnerRef(ReadSchema):
    id: int
    code: str
    name: str


class AddressIn(Schema):
    kind: AddressKind
    label: str | None = Field(None, max_length=100)
    line1: str = Field(min_length=1, max_length=200)
    line2: str | None = Field(None, max_length=200)
    postal_code: str = Field(min_length=1, max_length=10)
    city: str = Field(min_length=1, max_length=100)
    country_code: str = Field("FR", pattern=r"^[A-Z]{2}$")
    is_primary: bool = False


class AddressRead(ReadSchema):
    id: int
    kind: str
    label: str | None
    line1: str
    line2: str | None
    postal_code: str
    city: str
    country_code: str
    is_primary: bool


class ContactIn(Schema):
    first_name: str | None = Field(None, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    job_title: str | None = Field(None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    mobile: str | None = Field(None, max_length=30)
    notes: str | None = None
    is_primary: bool = False


class ContactRead(ReadSchema):
    id: int
    first_name: str | None
    last_name: str
    job_title: str | None
    email: str | None
    phone: str | None
    mobile: str | None
    notes: str | None
    is_primary: bool


class PartnerRead(ReadSchema):
    id: int
    code: str
    name: str
    legal_form: str | None
    siret: str | None
    vat_number: str | None
    is_supplier: bool
    is_customer: bool
    parent: PartnerRef | None
    email: str | None
    phone: str | None
    website: str | None
    notes: str | None
    is_active: bool
    supplier_account: str | None
    payment_method: str | None
    payment_days: int | None
    payment_end_of_month: bool
    currency: str
    lead_time_days: int | None
    min_order_amount: Decimal | None
    free_shipping_amount: Decimal | None
    bank_name: str | None
    iban: str | None
    bic: str | None
    addresses: list[AddressRead]
    contacts: list[ContactRead]
    version: int
    created_at: datetime
    updated_at: datetime


class PartnerListItem(Schema):
    id: int
    code: str
    name: str
    siret: str | None
    city: str | None  # ville du siège (ou de la première adresse)
    email: str | None
    phone: str | None
    contact_name: str | None  # interlocuteur principal
    is_supplier: bool
    is_customer: bool
    is_active: bool


class PartnerPage(Schema):
    items: list[PartnerListItem]
    total: int
