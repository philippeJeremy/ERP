"""Règles métier du module partners (tiers : fournisseurs, et bientôt clients)."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, DomainError, NotFound
from app.modules.org import public as org
from app.modules.partners import repository as repo
from app.modules.partners.models import Partner, PartnerAddress, PartnerContact
from app.modules.partners.schemas import (
    AddressIn,
    ContactIn,
    PartnerCreate,
    PartnerListItem,
    PartnerPage,
    PartnerUpdate,
)

# Champs pour lesquels « null » n'a pas de sens : on l'ignore au lieu d'échouer.
NOT_NULL_FIELDS = {
    "name",
    "is_supplier",
    "is_customer",
    "is_active",
    "payment_end_of_month",
    "currency",
    "customer_payment_end_of_month",
    "discount_pct",
}


class Invalid(DomainError):
    status_code = 422
    code = "invalide"


def list_partners(
    db: Session,
    *,
    role: str | None,
    q: str | None,
    active: bool | None,
    sort: str,
    order: str,
    limit: int,
    offset: int,
) -> PartnerPage:
    rows, total = repo.search(
        db,
        role=role,
        q=q.strip() if q else None,
        active=active,
        sort=sort,
        descending=order == "desc",
        limit=limit,
        offset=offset,
    )
    items = [
        PartnerListItem(
            id=p.id,
            code=p.code,
            name=p.name,
            siret=p.siret,
            city=city,
            email=p.email,
            phone=p.phone,
            contact_name=contact or None,
            is_supplier=p.is_supplier,
            is_customer=p.is_customer,
            is_active=p.is_active,
        )
        for p, city, contact in rows
    ]
    return PartnerPage(items=items, total=total)


def get_partner(db: Session, partner_id: int) -> Partner:
    partner = repo.get(db, partner_id)
    if partner is None:
        # RLS : un tiers d'une autre société est simplement « introuvable ».
        raise NotFound("Tiers introuvable")
    return partner


def _ensure_unique(db: Session, *, code: str | None, siret: str | None, partner_id: int | None):
    if code:
        other = repo.get_by_code(db, code)
        if other is not None and other.id != partner_id:
            raise Conflict(
                f"Le code « {code} » est déjà utilisé par « {other.name} »", code="code_existant"
            )
    if siret:
        other = repo.get_by_siret(db, siret)
        if other is not None and other.id != partner_id:
            raise Conflict(
                f"Le SIRET {siret} est déjà celui de « {other.name} » ({other.code})",
                code="siret_existant",
            )


def _check_parent(db: Session, parent_id: int | None, partner_id: int | None) -> None:
    """Le groupement doit exister dans la société, et pas de boucle (A → B → A)."""
    if parent_id is None:
        return
    if parent_id == partner_id:
        raise Invalid("Un tiers ne peut pas être son propre groupement")
    seen = {partner_id}
    current = repo.get(db, parent_id)
    if current is None:
        raise Invalid("Groupement introuvable")
    while current is not None:
        if current.id in seen:
            raise Invalid("Ce groupement créerait une boucle (A appartient à B qui appartient à A)")
        seen.add(current.id)
        current = current.parent


def create_partner(db: Session, data: PartnerCreate) -> Partner:
    if not (data.is_supplier or data.is_customer):
        raise Invalid("Un tiers doit être fournisseur, client, ou les deux")
    _ensure_unique(db, code=data.code, siret=data.siret, partner_id=None)
    _check_parent(db, data.parent_id, None)
    values = data.model_dump()
    # Pas de code saisi : le prochain numéro du compteur de la société (T00042).
    values["code"] = data.code or org.next_number(db, "partner")
    if data.is_customer and not data.customer_kind:
        values["customer_kind"] = "pro"
    partner = Partner(**values)
    db.add(partner)
    db.commit()
    return partner


def update_partner(db: Session, partner_id: int, data: PartnerUpdate) -> Partner:
    partner = get_partner(db, partner_id)
    if data.version != partner.version:
        raise Conflict(
            "La fiche a été modifiée entre-temps, rechargez-la", code="modifie_entre_temps"
        )
    changes = {
        k: v
        for k, v in data.model_dump(exclude_unset=True, exclude={"version"}).items()
        if not (v is None and k in NOT_NULL_FIELDS)
    }
    supplier = changes.get("is_supplier", partner.is_supplier)
    customer = changes.get("is_customer", partner.is_customer)
    if not (supplier or customer):
        raise Invalid("Un tiers doit être fournisseur, client, ou les deux")
    _ensure_unique(db, code=None, siret=changes.get("siret"), partner_id=partner.id)
    if "parent_id" in changes:
        _check_parent(db, changes["parent_id"], partner.id)
    for field, value in changes.items():
        setattr(partner, field, value)
    if partner.is_customer and not partner.customer_kind:
        partner.customer_kind = "pro"
    db.commit()
    return partner


def delete_partner(db: Session, partner_id: int) -> None:
    """Supprime un tiers SANS historique. Dès qu'il est référencé ailleurs (articles,
    commandes, factures), PostgreSQL refuse (clé étrangère) : on le désactive alors."""
    partner = get_partner(db, partner_id)
    try:
        db.delete(partner)
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict(
            "Ce tiers est utilisé (articles, commandes, factures…) : il ne peut pas être "
            "supprimé. Désactivez-le à la place.",
            code="tiers_utilise",
        ) from exc
    db.commit()


# --- Adresses et contacts -------------------------------------------------------------
# « Principal » est unique par type d'adresse (et parmi les contacts) : en cocher un
# décoche les autres, pour qu'il n'y ait jamais d'ambiguïté.


def _unset_primary_address(partner: Partner, kind: str, keep: PartnerAddress | None) -> None:
    for address in partner.addresses:
        if address is not keep and address.kind == kind:
            address.is_primary = False


def _find(items: list, item_id: int, label: str):
    for item in items:
        if item.id == item_id:
            return item
    raise NotFound(f"{label} introuvable")


def add_address(db: Session, partner_id: int, data: AddressIn) -> PartnerAddress:
    partner = get_partner(db, partner_id)
    address = PartnerAddress(**data.model_dump())
    # La première adresse d'un type devient principale d'office.
    if not any(a.kind == data.kind for a in partner.addresses):
        address.is_primary = True
    if address.is_primary:
        _unset_primary_address(partner, data.kind, address)
    partner.addresses.append(address)
    db.commit()
    return address


def update_address(
    db: Session, partner_id: int, address_id: int, data: AddressIn
) -> PartnerAddress:
    partner = get_partner(db, partner_id)
    address = _find(partner.addresses, address_id, "Adresse")
    for field, value in data.model_dump().items():
        setattr(address, field, value)
    if address.is_primary:
        _unset_primary_address(partner, address.kind, address)
    db.commit()
    return address


def delete_address(db: Session, partner_id: int, address_id: int) -> None:
    partner = get_partner(db, partner_id)
    address = _find(partner.addresses, address_id, "Adresse")
    partner.addresses.remove(address)
    if address.is_primary:
        # Une autre adresse du même type reprend le rôle de principale.
        same_kind = [a for a in partner.addresses if a.kind == address.kind]
        if same_kind:
            same_kind[0].is_primary = True
    db.commit()


def _unset_primary_contact(partner: Partner, keep: PartnerContact) -> None:
    for contact in partner.contacts:
        if contact is not keep:
            contact.is_primary = False


def add_contact(db: Session, partner_id: int, data: ContactIn) -> PartnerContact:
    partner = get_partner(db, partner_id)
    contact = PartnerContact(**data.model_dump())
    if not partner.contacts:
        contact.is_primary = True
    if contact.is_primary:
        _unset_primary_contact(partner, contact)
    partner.contacts.append(contact)
    db.commit()
    return contact


def update_contact(
    db: Session, partner_id: int, contact_id: int, data: ContactIn
) -> PartnerContact:
    partner = get_partner(db, partner_id)
    contact = _find(partner.contacts, contact_id, "Contact")
    for field, value in data.model_dump().items():
        setattr(contact, field, value)
    if contact.is_primary:
        _unset_primary_contact(partner, contact)
    db.commit()
    return contact


def delete_contact(db: Session, partner_id: int, contact_id: int) -> None:
    partner = get_partner(db, partner_id)
    contact = _find(partner.contacts, contact_id, "Contact")
    partner.contacts.remove(contact)
    if contact.is_primary and partner.contacts:
        partner.contacts[0].is_primary = True
    db.commit()
