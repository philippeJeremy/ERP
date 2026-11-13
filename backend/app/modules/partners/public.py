"""Interface publique du module partners : la SEULE chose que les autres modules importent.

Exemple : le futur module articles vérifiera qu'un fournisseur existe (dans la société
courante) avant de le lier à un article, via `partners.get_supplier(db, id)`.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.modules.partners import repository as repo
from app.modules.partners.models import Partner


def get_supplier(db: Session, partner_id: int) -> Partner:
    partner = repo.get(db, partner_id)
    if partner is None or not partner.is_supplier:
        raise NotFound("Fournisseur introuvable")
    return partner


def partner_names(db: Session, ids: set[int]) -> dict[int, tuple[str, str]]:
    """{id: (code, nom)} des tiers demandés (de la société courante, grâce à la RLS)."""
    if not ids:
        return {}
    rows = db.execute(select(Partner.id, Partner.code, Partner.name).where(Partner.id.in_(ids)))
    return {row.id: (row.code, row.name) for row in rows}


@dataclass
class SupplierTerms:
    """Ce dont les achats ont besoin d'un fournisseur (sans exposer le modèle)."""

    id: int
    code: str
    name: str
    is_active: bool
    currency: str
    payment_terms: str | None
    min_order_amount: Decimal | None
    free_shipping_amount: Decimal | None
    lead_time_days: int | None
    email: str | None
    phone: str | None
    siret: str | None
    vat_number: str | None
    gln: str | None
    order_address: list[str]  # lignes de l'adresse « commande » (sinon le siège)


PAYMENT_LABELS = {
    "virement": "virement",
    "prelevement": "prélèvement",
    "cheque": "chèque",
    "lcr": "LCR",
    "carte": "carte bancaire",
    "especes": "espèces",
}


def _payment_terms(p: Partner) -> str | None:
    parts = []
    if p.payment_days is not None:
        parts.append(
            "Comptant"
            if p.payment_days == 0
            else f"{p.payment_days} jours{' fin de mois' if p.payment_end_of_month else ''}"
        )
    if p.payment_method:
        parts.append(f"par {PAYMENT_LABELS.get(p.payment_method, p.payment_method)}")
    return ", ".join(parts) or None


def supplier_terms(db: Session, partner_id: int) -> SupplierTerms:
    p = get_supplier(db, partner_id)
    address = next(
        (
            a
            for kind in ("commande", "siege")
            for a in p.addresses
            if a.kind == kind and a.is_primary
        ),
        p.addresses[0] if p.addresses else None,
    )
    lines = []
    if address is not None:
        lines = [x for x in (address.line1, address.line2) if x]
        lines.append(f"{address.postal_code} {address.city}")
        if address.country_code != "FR":
            lines.append(address.country_code)
    return SupplierTerms(
        id=p.id, code=p.code, name=p.name, is_active=p.is_active, currency=p.currency,
        payment_terms=_payment_terms(p), min_order_amount=p.min_order_amount,
        free_shipping_amount=p.free_shipping_amount, lead_time_days=p.lead_time_days,
        email=p.email, phone=p.phone, siret=p.siret, vat_number=p.vat_number, gln=p.gln,
        order_address=lines,
    )  # fmt: skip


def search_partner_ids(db: Session, q: str) -> list[int]:
    """Ids des tiers dont le code ou le nom contient `q` (recherche des autres modules)."""
    pattern = f"%{q}%"
    return list(
        db.scalars(
            select(Partner.id).where(Partner.name.ilike(pattern) | Partner.code.ilike(pattern))
        )
    )


__all__ = ["SupplierTerms", "get_supplier", "partner_names", "search_partner_ids", "supplier_terms"]
