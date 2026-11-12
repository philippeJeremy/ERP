"""Accès aux données du module org. Uniquement des requêtes, aucune règle métier."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modules.org.models import Company, NumberSequence


def get_company(db: Session, company_id: int) -> Company | None:
    return db.get(Company, company_id)


def get_company_by_code(db: Session, code: str) -> Company | None:
    return db.scalar(select(Company).where(Company.code == code))


def get_company_by_siren(db: Session, siren: str) -> Company | None:
    return db.scalar(select(Company).where(Company.siren == siren))


def list_companies(db: Session, ids: set[int] | None = None) -> list[Company]:
    """Toutes les sociétés, ou seulement celles dont l'id est dans `ids`."""
    query = select(Company).order_by(Company.name)
    if ids is not None:
        query = query.where(Company.id.in_(ids))
    return list(db.scalars(query))


def delete_sequences(db: Session, company_id: int) -> None:
    db.execute(delete(NumberSequence).where(NumberSequence.company_id == company_id))


# Pas de filtre sur company_id dans les requêtes ci-dessous : la Row-Level Security
# de PostgreSQL ne renvoie de toute façon que les lignes de la société courante.


def list_sequences(db: Session) -> list[NumberSequence]:
    return list(db.scalars(select(NumberSequence).order_by(NumberSequence.code)))


def get_sequence(db: Session, code: str, *, for_update: bool = False) -> NumberSequence | None:
    query = select(NumberSequence).where(NumberSequence.code == code)
    if for_update:
        # Verrou sur la ligne jusqu'au commit : deux factures validées en même temps
        # attendent leur tour au lieu d'obtenir le même numéro.
        query = query.with_for_update()
    return db.scalar(query)
