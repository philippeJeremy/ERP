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


def _terms(days: int | None, end_of_month: bool, method: str | None) -> str | None:
    parts = []
    if days is not None:
        parts.append(
            "Comptant" if days == 0 else f"{days} jours{' fin de mois' if end_of_month else ''}"
        )
    if method:
        parts.append(f"par {PAYMENT_LABELS.get(method, method)}")
    return ", ".join(parts) or None


def _payment_terms(p: Partner) -> str | None:
    return _terms(p.payment_days, p.payment_end_of_month, p.payment_method)


def _address_lines(p: Partner, kinds: tuple[str, ...]) -> list[str]:
    """Lignes de la première adresse trouvée parmi `kinds` (la principale d'abord)."""
    candidates = [a for kind in kinds for a in p.addresses if a.kind == kind]
    candidates.sort(key=lambda a: (kinds.index(a.kind), not a.is_primary))
    address = candidates[0] if candidates else (p.addresses[0] if p.addresses else None)
    if address is None:
        return []
    lines = [x for x in (address.label, address.line1, address.line2) if x]
    lines.append(f"{address.postal_code} {address.city}")
    if address.country_code != "FR":
        lines.append(address.country_code)
    return lines


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


def get_customer(db: Session, partner_id: int) -> Partner:
    partner = repo.get(db, partner_id)
    if partner is None or not partner.is_customer:
        raise NotFound("Client introuvable")
    return partner


@dataclass
class CustomerTerms:
    """Ce dont les ventes ont besoin d'un client."""

    id: int
    code: str
    name: str  # « Garage Martin » ou « DUPONT Jean »
    kind: str  # pro / particulier
    is_active: bool
    payment_terms: str | None
    credit_limit: Decimal | None
    discount_pct: Decimal
    # Remise par famille d'article (« pneu », « piece », « accessoire ») ; None = la générale
    family_discounts: dict[str, Decimal | None]
    email: str | None
    phone: str | None
    siret: str | None
    vat_number: str | None
    vehicle_registration: str | None
    billing_address: list[str]
    delivery_address: list[str]

    def discount_for(self, kind: str | None) -> Decimal:
        family = self.family_discounts.get(kind or "")
        return family if family is not None else self.discount_pct


def customer_terms(db: Session, partner_id: int) -> CustomerTerms:
    p = get_customer(db, partner_id)
    display = f"{p.name} {p.first_name}" if p.first_name else p.name
    return CustomerTerms(
        id=p.id, code=p.code, name=display, kind=p.customer_kind or "pro",
        is_active=p.is_active,
        payment_terms=_terms(
            p.customer_payment_days, p.customer_payment_end_of_month, p.customer_payment_method
        ),
        credit_limit=p.credit_limit, discount_pct=p.discount_pct,
        family_discounts={
            "pneu": p.discount_tire_pct, "piece": p.discount_part_pct,
            "accessoire": p.discount_accessory_pct,
        },
        email=p.email, phone=p.phone, siret=p.siret, vat_number=p.vat_number,
        vehicle_registration=p.vehicle_registration,
        billing_address=_address_lines(p, ("facturation", "siege")),
        delivery_address=_address_lines(p, ("livraison", "siege", "facturation")),
    )  # fmt: skip


def search_partner_ids(db: Session, q: str) -> list[int]:
    """Ids des tiers dont le code ou le nom contient `q` (recherche des autres modules)."""
    pattern = f"%{q}%"
    return list(
        db.scalars(
            select(Partner.id).where(Partner.name.ilike(pattern) | Partner.code.ilike(pattern))
        )
    )


__all__ = [
    "CustomerTerms",
    "customer_terms",
    "get_customer",
    "SupplierTerms",
    "get_supplier",
    "partner_names",
    "search_partner_ids",
    "supplier_terms",
]
