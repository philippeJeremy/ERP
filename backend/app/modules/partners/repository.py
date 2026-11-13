"""Accès aux données du module partners. Uniquement des requêtes, aucune règle métier.

Pas de filtre sur company_id : la Row-Level Security ne renvoie que les lignes de la
société courante.
"""

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.modules.partners.models import Partner, PartnerAddress, PartnerContact

SORTABLE = {
    "code": Partner.code,
    "name": Partner.name,
    "created_at": Partner.created_at,
}


def get(db: Session, partner_id: int) -> Partner | None:
    return db.get(Partner, partner_id)


def get_by_code(db: Session, code: str) -> Partner | None:
    return db.scalar(select(Partner).where(Partner.code == code))


def get_by_siret(db: Session, siret: str) -> Partner | None:
    return db.scalar(select(Partner).where(Partner.siret == siret))


def _filtered(query: Select, *, role: str | None, q: str | None, active: bool | None) -> Select:
    if role == "supplier":
        query = query.where(Partner.is_supplier)
    elif role == "customer":
        query = query.where(Partner.is_customer)
    if active is not None:
        query = query.where(Partner.is_active == active)
    if q:
        # ILIKE : recherche insensible à la casse, n'importe où dans le texte.
        pattern = f"%{q.replace('%', r'\%').replace('_', r'\_')}%"
        contact_match = (
            select(PartnerContact.id)
            .where(PartnerContact.partner_id == Partner.id)
            .where(
                or_(
                    PartnerContact.last_name.ilike(pattern),
                    PartnerContact.first_name.ilike(pattern),
                )
            )
            .exists()
        )
        query = query.where(
            or_(
                Partner.code.ilike(pattern),
                Partner.name.ilike(pattern),
                Partner.siret.ilike(pattern.replace(" ", "")),
                Partner.email.ilike(pattern),
                contact_match,
            )
        )
    return query


def search(
    db: Session,
    *,
    role: str | None,
    q: str | None,
    active: bool | None,
    sort: str,
    descending: bool,
    limit: int,
    offset: int,
) -> tuple[list[tuple], int]:
    """Une page de la liste, avec la ville et l'interlocuteur principal, et le total."""
    total = db.scalar(_filtered(select(func.count(Partner.id)), role=role, q=q, active=active))

    # Sous-requêtes « corrélées » : pour chaque tiers, la ville de son adresse principale
    # (le siège d'abord) et le nom de son interlocuteur principal.
    city = (
        select(PartnerAddress.city)
        .where(PartnerAddress.partner_id == Partner.id)
        .order_by(
            (PartnerAddress.kind != "siege"),
            PartnerAddress.is_primary.desc(),
            PartnerAddress.id,
        )
        .limit(1)
        .scalar_subquery()
    )
    contact = (
        select(func.concat_ws(" ", PartnerContact.first_name, PartnerContact.last_name))
        .where(PartnerContact.partner_id == Partner.id)
        .order_by(PartnerContact.is_primary.desc(), PartnerContact.id)
        .limit(1)
        .scalar_subquery()
    )
    column = SORTABLE.get(sort, Partner.name)
    query = _filtered(
        select(Partner, city.label("city"), contact.label("contact_name")),
        role=role,
        q=q,
        active=active,
    )
    query = query.order_by(column.desc() if descending else column.asc(), Partner.id)
    rows = db.execute(query.limit(limit).offset(offset)).all()
    return [tuple(r) for r in rows], total or 0
