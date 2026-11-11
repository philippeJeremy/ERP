"""Règles métier du module org."""

from datetime import date

from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.db import set_db_context
from app.core.errors import Conflict, Forbidden, NotFound
from app.modules.auth import public as auth
from app.modules.org import repository as repo
from app.modules.org.models import Company, NumberSequence
from app.modules.org.schemas import CompanyCreate, CompanyUpdate, SequenceUpdate

# Compteurs créés automatiquement pour chaque nouvelle société.
DEFAULT_SEQUENCES = [
    ("quote", "Devis", "DV-{year}-"),
    ("sales_order", "Commandes client", "CC-{year}-"),
    ("purchase_order", "Commandes fournisseur", "CF-{year}-"),
    ("invoice", "Factures", "FA-{year}-"),
    ("credit_note", "Avoirs", "AV-{year}-"),
]


def list_companies_for(db: Session, ctx: RequestContext) -> list[Company]:
    if ctx.is_superuser:
        return repo.list_companies(db)
    return repo.list_companies(db, auth.company_ids_of(db, ctx.user_id))


def get_company(db: Session, ctx: RequestContext, company_id: int) -> Company:
    if not ctx.is_superuser and company_id not in auth.company_ids_of(db, ctx.user_id):
        raise NotFound(
            "Société introuvable"
        )  # 404 plutôt que 403 : on ne révèle pas qu'elle existe
    company = repo.get_company(db, company_id)
    if company is None:
        raise NotFound("Société introuvable")
    return company


def create_company(db: Session, ctx: RequestContext, data: CompanyCreate) -> Company:
    if repo.get_company_by_code(db, data.code):
        raise Conflict(f"Le code société « {data.code} » existe déjà")

    company = Company(**data.model_dump())
    db.add(company)
    db.flush()  # envoie l'INSERT pour obtenir company.id sans terminer la transaction

    # Les compteurs sont protégés par la RLS : on bascule temporairement le contexte
    # sur la nouvelle société, sinon PostgreSQL refuserait l'insertion (WITH CHECK).
    previous_company = ctx.company_id
    set_db_context(db, user_id=ctx.user_id, company_id=company.id)
    for code, label, prefix in DEFAULT_SEQUENCES:
        db.add(NumberSequence(company_id=company.id, code=code, label=label, prefix=prefix))
    db.flush()
    set_db_context(db, user_id=ctx.user_id, company_id=previous_company)

    # Le créateur devient administrateur de la société.
    auth.grant_role(db, user_id=ctx.user_id, company_id=company.id, role_code="admin")
    db.commit()
    return company


def update_company(
    db: Session, ctx: RequestContext, company_id: int, data: CompanyUpdate
) -> Company:
    if not ctx.is_superuser and company_id != ctx.company_id:
        raise Forbidden("Vous ne pouvez modifier que la société courante")
    company = repo.get_company(db, company_id)
    if company is None:
        raise NotFound("Société introuvable")
    if data.version != company.version:
        # L'utilisateur travaillait sur une version périmée de la fiche.
        raise Conflict(
            "La fiche a été modifiée entre-temps, rechargez-la", code="modifie_entre_temps"
        )

    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    for field, value in changes.items():
        setattr(company, field, value)
    db.commit()
    return company


def list_sequences(db: Session) -> list[NumberSequence]:
    return repo.list_sequences(db)


def update_sequence(db: Session, code: str, data: SequenceUpdate) -> NumberSequence:
    seq = repo.get_sequence(db, code, for_update=True)
    if seq is None:
        raise NotFound(f"Séquence « {code} » introuvable")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(seq, field, value)
    db.commit()
    return seq


def next_number(db: Session, code: str, *, today: date | None = None) -> str:
    """Attribue le prochain numéro d'une séquence de la société courante.

    Ne fait PAS de commit : le numéro n'est consommé que si la transaction de
    l'appelant (ex. la validation d'une facture) réussit. En cas d'erreur, rollback
    → le numéro est rendu, il n'y a pas de trou dans la numérotation.
    """
    year = (today or date.today()).year
    seq = repo.get_sequence(db, code, for_update=True)
    if seq is None:
        raise NotFound(f"Séquence « {code} » introuvable pour cette société")
    if seq.reset_yearly and seq.current_year != year:
        seq.current_year = year
        seq.next_value = 1
    value = seq.next_value
    seq.next_value = value + 1
    db.flush()
    return seq.prefix.replace("{year}", str(year)) + str(value).zfill(seq.padding)
