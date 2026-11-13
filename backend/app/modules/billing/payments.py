"""Règlements clients, lettrage, échéancier, relances et encours."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.modules.billing import invoices as inv
from app.modules.billing.common import ZERO, Invalid, money, now
from app.modules.billing.models import Allocation, Invoice, Payment
from app.modules.billing.schemas import (
    AgingRow,
    Allocate,
    CustomerAccount,
    PaymentIn,
    PaymentPage,
    PaymentRead,
    Receivables,
)
from app.modules.org import public as org
from app.modules.partners import public as partners
from app.modules.sales import public as sales


def _get(db: Session, payment_id: int) -> Payment:
    payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if payment is None:
        raise NotFound("Règlement introuvable")
    return payment


def read(db: Session, payment: Payment, name: str | None = None) -> PaymentRead:
    rows = list(db.scalars(select(Allocation).where(Allocation.payment_id == payment.id)))
    allocated = sum((x.amount for x in rows), ZERO)
    if name is None:
        name = partners.partner_names(db, {payment.customer_id})[payment.customer_id][1]
    return PaymentRead(
        id=payment.id, number=payment.number, customer_id=payment.customer_id,
        customer_name=name, paid_on=payment.paid_on, amount=payment.amount,
        method=payment.method, reference=payment.reference, note=payment.note,
        allocated=allocated, unallocated=payment.amount - allocated,
        allocations=inv.describe_allocations(db, rows), created_at=payment.created_at,
    )  # fmt: skip


def _unallocated(db: Session, payment: Payment) -> Decimal:
    used = db.scalar(
        select(func.coalesce(func.sum(Allocation.amount), 0)).where(
            Allocation.payment_id == payment.id
        )
    )
    return payment.amount - Decimal(used)


def _open_invoices(db: Session, customer_id: int) -> list[Invoice]:
    """Factures émises non soldées, la plus ancienne échéance d'abord (verrouillées)."""
    return list(
        db.scalars(
            select(Invoice)
            .where(
                Invoice.customer_id == customer_id,
                Invoice.kind == "facture",
                Invoice.status == "emise",
                Invoice.total_ttc > Invoice.paid_amount,
            )
            .order_by(Invoice.due_date, Invoice.id)
            .with_for_update()
        )
    )


def _apply(db: Session, payment: Payment, allocations: list | None) -> None:
    """Lettre le règlement : sur les factures indiquées, sinon les plus anciennes d'abord."""
    left = _unallocated(db, payment)
    if allocations is None:
        for invoice in _open_invoices(db, payment.customer_id):
            if left <= 0:
                break
            amount = min(left, inv.balance(invoice))
            inv.allocate(db, invoice, amount, payment=payment)
            left -= amount
        return
    total = sum((a.amount for a in allocations), ZERO)
    if total > left:
        raise Invalid(f"Les affectations ({total} €) dépassent le montant disponible ({left} €)")
    for a in allocations:
        invoice = inv.get(db, a.invoice_id, for_update=True)
        inv.allocate(db, invoice, a.amount, payment=payment)


def create_payment(db: Session, data: PaymentIn) -> PaymentRead:
    partners.get_customer(db, data.customer_id)
    payment = Payment(
        number=org.next_number(db, "payment"),
        customer_id=data.customer_id,
        paid_on=data.paid_on,
        amount=data.amount,
        method=data.method,
        reference=data.reference,
        note=data.note,
    )
    db.add(payment)
    db.flush()
    _apply(db, payment, data.allocations)
    db.commit()
    return read(db, payment)


def allocate_payment(db: Session, payment_id: int, data: Allocate) -> PaymentRead:
    payment = _get(db, payment_id)
    _apply(db, payment, data.allocations)
    db.commit()
    return read(db, payment)


def delete_payment(db: Session, payment_id: int) -> None:
    """Supprime un règlement saisi par erreur : son lettrage est défait."""
    payment = _get(db, payment_id)
    for allocation in db.scalars(select(Allocation).where(Allocation.payment_id == payment.id)):
        invoice = inv.get(db, allocation.invoice_id, for_update=True)
        invoice.paid_amount -= allocation.amount
        db.delete(allocation)
    db.flush()
    db.delete(payment)
    db.commit()


def unallocate(db: Session, allocation_id: int) -> None:
    allocation = db.get(Allocation, allocation_id)
    if allocation is None:
        raise NotFound("Lettrage introuvable")
    invoice = inv.get(db, allocation.invoice_id, for_update=True)
    invoice.paid_amount -= allocation.amount
    if allocation.credit_note_id:
        note = inv.get(db, allocation.credit_note_id, for_update=True)
        note.paid_amount -= allocation.amount
    db.delete(allocation)
    db.commit()


def list_payments(
    db: Session, *, customer_id: int | None, unallocated: bool, limit: int, offset: int
) -> PaymentPage:
    query = select(Payment)
    if customer_id is not None:
        query = query.where(Payment.customer_id == customer_id)
    if unallocated:
        used = (
            select(func.coalesce(func.sum(Allocation.amount), 0))
            .where(Allocation.payment_id == Payment.id)
            .scalar_subquery()
        )
        query = query.where(Payment.amount > used)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(
        db.scalars(
            query.order_by(Payment.paid_on.desc(), Payment.id.desc()).limit(limit).offset(offset)
        )
    )
    names = partners.partner_names(db, {x.customer_id for x in rows})
    return PaymentPage(items=[read(db, x, names[x.customer_id][1]) for x in rows], total=total)


# --- Compte client, échéancier, encours ------------------------------------------------


def customer_account(db: Session, customer_id: int) -> CustomerAccount:
    terms = partners.customer_terms(db, customer_id)
    rows = list(
        db.scalars(
            select(Invoice)
            .where(
                Invoice.customer_id == customer_id,
                Invoice.status == "emise",
                Invoice.total_ttc > Invoice.paid_amount,
            )
            .order_by(Invoice.due_date, Invoice.id)
        )
    )
    names = {customer_id: (terms.code, terms.name)}
    factures = [inv.list_item(db, x, names) for x in rows if x.kind == "facture"]
    notes = [inv.list_item(db, x, names) for x in rows if x.kind == "avoir"]
    payments = [
        read(db, p, terms.name)
        for p in db.scalars(
            select(Payment).where(Payment.customer_id == customer_id).order_by(Payment.paid_on)
        )
    ]
    payments = [p for p in payments if p.unallocated > 0]
    return CustomerAccount(
        customer_id=customer_id,
        customer_name=terms.name,
        invoices=factures,
        credit_notes=notes,
        unallocated_payments=payments,
        total_due=sum((x.balance for x in factures), ZERO),
        overdue=sum((x.balance for x in factures if x.days_late > 0), ZERO),
        available_credit=sum((x.balance for x in notes), ZERO)
        + sum((p.unallocated for p in payments), ZERO),
        uninvoiced=inv.uninvoiced_ttc(db, customer_id),
    )


def customer_outstanding(db: Session, customer_id: int) -> Decimal:
    """Pour l'encours des ventes : livré non facturé + factures impayées − crédits."""
    due = db.scalar(
        select(func.coalesce(func.sum(Invoice.total_ttc - Invoice.paid_amount), 0)).where(
            Invoice.customer_id == customer_id,
            Invoice.status == "emise",
            Invoice.kind == "facture",
        )
    )
    credit = db.scalar(
        select(func.coalesce(func.sum(Invoice.total_ttc - Invoice.paid_amount), 0)).where(
            Invoice.customer_id == customer_id,
            Invoice.status == "emise",
            Invoice.kind == "avoir",
        )
    )
    unallocated = ZERO
    for payment in db.scalars(select(Payment).where(Payment.customer_id == customer_id)):
        unallocated += _unallocated(db, payment)
    return money(Decimal(due) - Decimal(credit) - unallocated + inv.uninvoiced_ttc(db, customer_id))


sales.register_outstanding_source(customer_outstanding)


def receivables(db: Session) -> Receivables:
    """Balance âgée : ce que chaque client doit, par ancienneté de retard."""
    rows = db.scalars(
        select(Invoice).where(
            Invoice.status == "emise",
            Invoice.kind == "facture",
            Invoice.total_ttc > Invoice.paid_amount,
        )
    )
    today = date.today()
    by_customer: dict[int, AgingRow] = {}
    for invoice in rows:
        row = by_customer.setdefault(
            invoice.customer_id,
            AgingRow(
                customer_id=invoice.customer_id,
                customer_name=invoice.customer_name or "",
                not_due=ZERO,
                late_30=ZERO,
                late_60=ZERO,
                late_more=ZERO,
                total=ZERO,
                last_reminder_at=None,
            ),  # fmt: skip
        )
        amount = inv.balance(invoice)
        late = inv.days_late(invoice, today)
        if late == 0:
            row.not_due += amount
        elif late <= 30:
            row.late_30 += amount
        elif late <= 60:
            row.late_60 += amount
        else:
            row.late_more += amount
        row.total += amount
        if invoice.last_reminder_at and (
            row.last_reminder_at is None or invoice.last_reminder_at > row.last_reminder_at
        ):
            row.last_reminder_at = invoice.last_reminder_at
    result = sorted(
        by_customer.values(),
        key=lambda r: (-(r.late_30 + r.late_60 + r.late_more), r.customer_name),
    )
    totals = AgingRow(
        customer_id=0, customer_name="Total",
        not_due=sum((r.not_due for r in result), ZERO), late_30=sum((r.late_30 for r in result), ZERO),  # noqa: E501
        late_60=sum((r.late_60 for r in result), ZERO),
        late_more=sum((r.late_more for r in result), ZERO),
        total=sum((r.total for r in result), ZERO), last_reminder_at=None,
    )  # fmt: skip
    return Receivables(rows=result, totals=totals)


def overdue_invoices(db: Session, customer_id: int) -> list[Invoice]:
    return [x for x in _open_invoices(db, customer_id) if inv.days_late(x) > 0]


def mark_reminded(db: Session, customer_id: int) -> list[Invoice]:
    """Note la relance sur chaque facture en retard du client (le PDF la matérialise)."""
    invoices = overdue_invoices(db, customer_id)
    if not invoices:
        raise Invalid("Ce client n'a aucune facture en retard")
    stamp = now()
    for invoice in invoices:
        invoice.reminder_count += 1
        invoice.last_reminder_at = stamp
    db.commit()
    return invoices
