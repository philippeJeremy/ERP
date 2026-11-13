"""Outils communs du module facturation : montants, échéances, réglages, erreurs."""

import calendar
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.modules.billing.models import BillingSettings

CENT = Decimal("0.01")
ZERO = Decimal(0)


class Invalid(DomainError):
    status_code = 422
    code = "invalide"


def now() -> datetime:
    return datetime.now(UTC)


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def line_total(quantity: Decimal, price: Decimal, discount: Decimal) -> Decimal:
    """Quantité × prix × (1 − remise %), arrondi au centime (le même calcul que les ventes)."""
    return money(quantity * price * (Decimal(100) - discount) / Decimal(100))


def due_date(start: date, days: int | None, end_of_month: bool) -> date:
    """Échéance : « 30 jours » = date + 30 ; « 45 jours fin de mois » = date + 45 jours,
    reportée au dernier jour de ce mois-là."""
    result = start + timedelta(days=days or 0)
    if end_of_month:
        result = result.replace(day=calendar.monthrange(result.year, result.month)[1])
    return result


def get_settings(db: Session) -> BillingSettings:
    settings = db.scalar(select(BillingSettings))
    if settings is None:
        # Valeurs par défaut (non enregistrées tant qu'on ne modifie pas les réglages).
        settings = BillingSettings(
            default_payment_days=30, default_vat_rate=Decimal(20), customer_account="411000",
            supplier_account="401000", sales_goods_account="707000",
            sales_services_account="706000", eco_fee_account="708500",
            vat_collected_account="445710", purchases_account="607000",
            vat_deductible_account="445660", bank_account="512000", cash_account="530000",
            sales_journal="VT", purchases_journal="AC", bank_journal="BQ",
        )  # fmt: skip
    return settings


def save_settings(db: Session, values: dict) -> BillingSettings:
    settings = db.scalar(select(BillingSettings))
    if settings is None:
        settings = BillingSettings()
        db.add(settings)
    for field, value in values.items():
        setattr(settings, field, value)
    db.commit()
    return settings
