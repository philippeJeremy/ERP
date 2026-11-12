"""Règles métier du module org."""

from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.db import set_db_context
from app.core.errors import Conflict, Forbidden, NotFound
from app.modules.auth import public as auth
from app.modules.org import repository as repo
from app.modules.org.models import Company, NumberSequence
from app.modules.org.schemas import CompanyCreate, CompanyUpdate, SequenceUpdate

NOT_NULL_FIELDS = {"name", "country_code", "currency", "is_active"}

# Compteurs créés automatiquement pour chaque nouvelle société.
DEFAULT_SEQUENCES = [
    ("quote", "Devis", "DV-{year}-"),
    ("sales_order", "Commandes client", "CC-{year}-"),
    ("purchase_order", "Commandes fournisseur", "CF-{year}-"),
    ("invoice", "Factures", "FA-{year}-"),
    ("credit_note", "Avoirs", "AV-{year}-"),
]


def _refuse_inactive_company(db: Session, company_id: int) -> None:
    """Branché sur l'authentification : une société désactivée n'est plus utilisable
    (sauf par un super-administrateur, qui doit pouvoir la réactiver)."""
    company = repo.get_company(db, company_id)
    if company is not None and not company.is_active:
        raise Forbidden("Cette société est désactivée", code="societe_desactivee")


auth.add_company_guard(_refuse_inactive_company)


def list_companies_for(db: Session, ctx: RequestContext) -> list[Company]:
    if ctx.is_superuser:
        return repo.list_companies(db)
    companies = repo.list_companies(db, auth.company_ids_of(db, ctx.user_id))
    return [c for c in companies if c.is_active]


def get_company(db: Session, ctx: RequestContext, company_id: int) -> Company:
    if not ctx.is_superuser and company_id not in auth.company_ids_of(db, ctx.user_id):
        raise NotFound(
            "Société introuvable"
        )  # 404 plutôt que 403 : on ne révèle pas qu'elle existe
    company = repo.get_company(db, company_id)
    if company is None:
        raise NotFound("Société introuvable")
    return company


def _ensure_siren_free(db: Session, siren: str | None, company_id: int | None) -> None:
    """Un SIREN identifie UNE entité juridique : deux sociétés ne peuvent pas le partager."""
    if not siren:
        return
    other = repo.get_company_by_siren(db, siren)
    if other is not None and other.id != company_id:
        raise Conflict(
            f"Le SIREN {siren} est déjà celui de « {other.name} »", code="siren_existant"
        )


def create_company(db: Session, ctx: RequestContext, data: CompanyCreate) -> Company:
    if repo.get_company_by_code(db, data.code):
        raise Conflict(f"Le code société « {data.code} » existe déjà")

    _ensure_siren_free(db, data.siren, None)

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
    if (
        "is_active" in changes
        and changes["is_active"] != company.is_active
        and not ctx.is_superuser
    ):
        # Sinon un administrateur pourrait couper l'accès à tout le monde, lui compris.
        raise Forbidden("Seul un super-administrateur peut activer ou désactiver une société")
    if changes.get("siren"):
        _ensure_siren_free(db, changes["siren"], company.id)
    for field, value in changes.items():
        if value is None and field in NOT_NULL_FIELDS:
            continue  # « null » n'a pas de sens pour ces champs : on ignore
        setattr(company, field, value)
    db.commit()
    return company


def delete_company(db: Session, ctx: RequestContext, company_id: int) -> None:
    """Supprime une société VIDE (créée par erreur, société de test).

    Une société qui a des documents (tiers, commandes, factures…) ne se supprime pas :
    les factures doivent être conservées 10 ans. PostgreSQL refuse alors la suppression
    (clés étrangères) et on demande de la désactiver à la place.
    """
    company = repo.get_company(db, company_id)
    if company is None:
        raise NotFound("Société introuvable")
    if len(repo.list_companies(db)) == 1:
        raise Conflict("Impossible de supprimer la dernière société", code="derniere_societe")
    try:
        # Les compteurs sont protégés par la RLS : il faut « être » dans la société.
        set_db_context(db, user_id=ctx.user_id, company_id=company.id)
        repo.delete_sequences(db, company.id)
        auth.revoke_company_access(db, company.id)
        db.delete(company)
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict(
            "Cette société contient des données : elle ne peut pas être supprimée. "
            "Désactivez-la à la place.",
            code="societe_non_vide",
        ) from exc
    set_db_context(db, user_id=ctx.user_id, company_id=None)
    db.commit()


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
