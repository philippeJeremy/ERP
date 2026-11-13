"""Factures fournisseur : saisie depuis les réceptions, contrôle, bon à payer, paiement.

Le contrôle « à trois voies » compare, pour chaque ligne, ce qui est FACTURÉ à ce qui
a été COMMANDÉ (prix net) et REÇU (quantité). Les écarts sont listés ; une facture
avec écart ne passe en « bon à payer » qu'avec une justification écrite.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.errors import Conflict, NotFound
from app.modules.billing.common import ZERO, Invalid, due_date, get_settings, money, now
from app.modules.billing.models import SupplierInvoice, SupplierInvoiceLine, SupplierPayment
from app.modules.billing.schemas import (
    Approve,
    ReceptionToBill,
    SupplierInvoiceCreate,
    SupplierInvoiceListItem,
    SupplierInvoicePage,
    SupplierInvoiceRead,
    SupplierInvoiceUpdate,
    SupplierLineIn,
    SupplierLineRead,
    SupplierPaymentIn,
    SupplierPaymentRead,
    VatRow,
)
from app.modules.org import public as org
from app.modules.partners import public as partners
from app.modules.purchasing import public as purchasing

TOLERANCE = Decimal("0.05")  # écart de total accepté (arrondis)


def _total(quantity: Decimal, price: Decimal) -> Decimal:
    return money(quantity * price)


def computed(invoice: SupplierInvoice) -> tuple[Decimal, Decimal]:
    bases: dict[Decimal, Decimal] = {}
    for line in invoice.lines:
        bases[line.vat_rate] = bases.get(line.vat_rate, ZERO) + line.line_total
    ht = sum(bases.values(), ZERO)
    vat = sum((money(b * r / 100) for r, b in bases.items()), ZERO)
    return ht, vat


def vat_rows(invoice: SupplierInvoice) -> list[VatRow]:
    bases: dict[Decimal, Decimal] = {}
    for line in invoice.lines:
        bases[line.vat_rate] = bases.get(line.vat_rate, ZERO) + line.line_total
    return [VatRow(rate=r, base=b, vat=money(b * r / 100)) for r, b in sorted(bases.items())]


def gaps(invoice: SupplierInvoice) -> list[str]:
    found = []
    for line in invoice.lines:
        if line.expected_quantity is not None and line.quantity != line.expected_quantity:
            found.append(
                f"Ligne {line.line_no} ({line.designation[:40]}) : {line.quantity.normalize():f} "
                f"facturé(s), {line.expected_quantity.normalize():f} reçu(s)"
            )
        if line.expected_price is not None and abs(line.unit_price - line.expected_price) > Decimal(
            "0.005"
        ):
            found.append(
                f"Ligne {line.line_no} ({line.designation[:40]}) : prix facturé "
                f"{line.unit_price.normalize():f} €, commandé {line.expected_price.normalize():f} €"
            )
    ht, vat = computed(invoice)
    if abs(invoice.total_ht - ht) > TOLERANCE:
        found.append(f"Total HT saisi {invoice.total_ht:.2f} €, lignes {ht:.2f} €")
    if abs(invoice.total_vat - vat) > TOLERANCE:
        found.append(f"TVA saisie {invoice.total_vat:.2f} €, calculée {vat:.2f} €")
    if abs(invoice.total_ttc - invoice.total_ht - invoice.total_vat) > Decimal("0.01"):
        found.append("TTC saisi ≠ HT + TVA saisis")
    return found


def _get(db: Session, invoice_id: int, *, for_update: bool = False) -> SupplierInvoice:
    query = select(SupplierInvoice).where(SupplierInvoice.id == invoice_id)
    if for_update:
        query = query.with_for_update(of=SupplierInvoice)
    invoice = db.scalar(query)
    if invoice is None:
        raise NotFound("Facture fournisseur introuvable")
    return invoice


def read(db: Session, invoice: SupplierInvoice) -> SupplierInvoiceRead:
    ht, vat = computed(invoice)
    name = partners.partner_names(db, {invoice.partner_id})[invoice.partner_id][1]
    payments = list(
        db.scalars(
            select(SupplierPayment)
            .where(SupplierPayment.supplier_invoice_id == invoice.id)
            .order_by(SupplierPayment.paid_on)
        )
    )
    return SupplierInvoiceRead(
        id=invoice.id, number=invoice.number, status=invoice.status,
        partner_id=invoice.partner_id, partner_name=name,
        supplier_number=invoice.supplier_number, invoice_date=invoice.invoice_date,
        due_date=invoice.due_date, total_ht=invoice.total_ht, total_vat=invoice.total_vat,
        total_ttc=invoice.total_ttc, computed_ht=ht, computed_vat=vat, gaps=gaps(invoice),
        paid_amount=invoice.paid_amount, balance=invoice.total_ttc - invoice.paid_amount,
        note=invoice.note, approved_at=invoice.approved_at, approval_note=invoice.approval_note,
        lines=[
            SupplierLineRead(
                id=x.id, line_no=x.line_no, reception_line_id=x.reception_line_id,
                reception_number=x.reception_number, order_number=x.order_number,
                article_id=x.article_id, designation=x.designation, quantity=x.quantity,
                unit_price=x.unit_price, expected_quantity=x.expected_quantity,
                expected_price=x.expected_price, vat_rate=x.vat_rate, line_total=x.line_total,
                qty_gap=x.quantity - x.expected_quantity if x.expected_quantity is not None else None,  # noqa: E501
                price_gap=x.unit_price - x.expected_price if x.expected_price is not None else None,
            )
            for x in invoice.lines
        ],
        payments=[SupplierPaymentRead.model_validate(p) for p in payments],
        version=invoice.version, created_at=invoice.created_at,
    )  # fmt: skip


def get_invoice(db: Session, invoice_id: int) -> SupplierInvoiceRead:
    return read(db, _get(db, invoice_id))


def list_invoices(
    db: Session,
    *,
    status: str | None,
    unpaid: bool,
    partner_id: int | None,
    q: str | None,
    limit: int,
    offset: int,
) -> SupplierInvoicePage:
    query = select(SupplierInvoice)
    if status:
        query = query.where(SupplierInvoice.status == status)
    if unpaid:
        query = query.where(
            SupplierInvoice.status == "bon_a_payer",
            SupplierInvoice.total_ttc > SupplierInvoice.paid_amount,
        )
    if partner_id is not None:
        query = query.where(SupplierInvoice.partner_id == partner_id)
    q = (q or "").strip()
    if q:
        ids = partners.search_partner_ids(db, q)
        condition = SupplierInvoice.number.ilike(f"%{q}%") | SupplierInvoice.supplier_number.ilike(
            f"%{q}%"
        )
        if ids:
            condition = condition | SupplierInvoice.partner_id.in_(ids)
        query = query.where(condition)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(
        db.scalars(
            query.order_by(SupplierInvoice.invoice_date.desc(), SupplierInvoice.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    names = partners.partner_names(db, {x.partner_id for x in rows})
    return SupplierInvoicePage(
        items=[
            SupplierInvoiceListItem(
                id=x.id,
                number=x.number,
                status=x.status,
                partner_id=x.partner_id,
                partner_name=names[x.partner_id][1],
                supplier_number=x.supplier_number,
                invoice_date=x.invoice_date,
                due_date=x.due_date,
                total_ttc=x.total_ttc,
                balance=x.total_ttc - x.paid_amount,
                has_gaps=bool(gaps(x)),
            )  # fmt: skip
            for x in rows
        ],
        total=total,
    )


def _invoiced_reception_lines(db: Session, ids: set[int] | None = None) -> set[int]:
    query = (
        select(SupplierInvoiceLine.reception_line_id)
        .join(SupplierInvoice, SupplierInvoice.id == SupplierInvoiceLine.supplier_invoice_id)
        .where(
            SupplierInvoice.status != "annulee", SupplierInvoiceLine.reception_line_id.is_not(None)
        )
    )
    if ids is not None:
        query = query.where(SupplierInvoiceLine.reception_line_id.in_(ids))
    return set(db.scalars(query))


def receptions_to_bill(db: Session, partner_id: int) -> list[ReceptionToBill]:
    receptions = purchasing.receptions_for_supplier(db, partner_id)
    done = _invoiced_reception_lines(db, {x.reception_line_id for r in receptions for x in r.lines})
    result = []
    for r in receptions:
        lines = [x for x in r.lines if x.reception_line_id not in done]
        if not lines:
            continue
        result.append(
            ReceptionToBill(
                id=r.id,
                number=r.number,
                received_on=r.received_on,
                delivery_note=r.delivery_note,
                order_number=r.order_number,
                total_ht=sum((_total(x.quantity, x.net_price) for x in lines), ZERO),
                line_count=len(lines),
            )  # fmt: skip
        )
    return result


def create(db: Session, data: SupplierInvoiceCreate) -> SupplierInvoiceRead:
    terms = partners.supplier_terms(db, data.partner_id)
    vat = get_settings(db).default_vat_rate
    invoice = SupplierInvoice(
        number=org.next_number(db, "supplier_invoice"),
        partner_id=data.partner_id,
        supplier_number=data.supplier_number.strip(),
        invoice_date=data.invoice_date,
        due_date=data.due_date
        or due_date(data.invoice_date, terms.payment_days, terms.payment_end_of_month),
        total_ht=data.total_ht,
        total_vat=data.total_vat,
        total_ttc=data.total_ttc,
        note=data.note,
    )
    receptions = purchasing.receptions_by_ids(db, set(data.reception_ids))
    if len(receptions) != len(set(data.reception_ids)):
        raise NotFound("Réception introuvable")
    done = _invoiced_reception_lines(db, {x.reception_line_id for r in receptions for x in r.lines})
    line_no = 0
    for r in receptions:
        if r.partner_id != data.partner_id:
            raise Invalid(f"La réception {r.number} est celle d'un autre fournisseur")
        for x in r.lines:
            if x.reception_line_id in done:
                continue
            line_no += 1
            invoice.lines.append(
                SupplierInvoiceLine(
                    line_no=line_no,
                    reception_line_id=x.reception_line_id,
                    reception_number=r.number,
                    order_number=r.order_number,
                    article_id=x.article_id,
                    designation=(f"{x.supplier_ref} — " if x.supplier_ref else "") + x.designation,
                    quantity=x.quantity,
                    unit_price=x.net_price,
                    expected_quantity=x.quantity,
                    expected_price=x.net_price,
                    vat_rate=vat,
                    line_total=_total(x.quantity, x.net_price),
                )  # fmt: skip
            )
    db.add(invoice)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict(
            f"La facture n° {data.supplier_number} de ce fournisseur est déjà saisie",
            code="doublon",
        ) from exc
    db.commit()
    return read(db, invoice)


def _draft(db: Session, invoice_id: int) -> SupplierInvoice:
    invoice = _get(db, invoice_id, for_update=True)
    if invoice.status != "brouillon":
        raise Conflict(
            "La facture est validée : elle ne se modifie plus", code="statut_incompatible"
        )
    return invoice


def update(db: Session, invoice_id: int, data: SupplierInvoiceUpdate) -> SupplierInvoiceRead:
    invoice = _draft(db, invoice_id)
    if data.version != invoice.version:
        raise Conflict("La facture a été modifiée entre-temps", code="modifie_entre_temps")
    for field, value in data.model_dump(exclude_unset=True, exclude={"version"}).items():
        if value is not None or field in ("note", "due_date"):
            setattr(invoice, field, value)
    invoice.updated_at = now()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict(
            "Ce n° de facture est déjà saisi pour ce fournisseur", code="doublon"
        ) from exc
    return read(db, invoice)


def add_line(db: Session, invoice_id: int, data: SupplierLineIn) -> SupplierInvoiceRead:
    invoice = _draft(db, invoice_id)
    if not data.designation:
        raise Invalid("Désignation obligatoire (port, frais, remise…)")
    invoice.lines.append(
        SupplierInvoiceLine(
            line_no=max((x.line_no for x in invoice.lines), default=0) + 1,
            designation=data.designation,
            quantity=data.quantity,
            unit_price=data.unit_price,
            vat_rate=data.vat_rate
            if data.vat_rate is not None
            else get_settings(db).default_vat_rate,
            line_total=_total(data.quantity, data.unit_price),
        )  # fmt: skip
    )
    invoice.updated_at = now()
    db.commit()
    return read(db, invoice)


def update_line(
    db: Session, invoice_id: int, line_id: int, data: SupplierLineIn
) -> SupplierInvoiceRead:
    invoice = _draft(db, invoice_id)
    line = next((x for x in invoice.lines if x.id == line_id), None)
    if line is None:
        raise NotFound("Ligne introuvable")
    if data.designation and line.reception_line_id is None:
        line.designation = data.designation
    line.quantity = data.quantity
    line.unit_price = data.unit_price
    if data.vat_rate is not None:
        line.vat_rate = data.vat_rate
    line.line_total = _total(line.quantity, line.unit_price)
    invoice.updated_at = now()
    db.commit()
    return read(db, invoice)


def delete_line(db: Session, invoice_id: int, line_id: int) -> SupplierInvoiceRead:
    invoice = _draft(db, invoice_id)
    line = next((x for x in invoice.lines if x.id == line_id), None)
    if line is None:
        raise NotFound("Ligne introuvable")
    invoice.lines.remove(line)
    invoice.updated_at = now()
    db.commit()
    return read(db, invoice)


def approve(
    db: Session, ctx: RequestContext, invoice_id: int, data: Approve
) -> SupplierInvoiceRead:
    invoice = _draft(db, invoice_id)
    if data.version != invoice.version:
        raise Conflict("La facture a été modifiée entre-temps", code="modifie_entre_temps")
    if not invoice.lines:
        raise Invalid("La facture n'a aucune ligne")
    found = gaps(invoice)
    if found and not (data.note or "").strip():
        raise Conflict(
            "Écarts constatés : " + " ; ".join(found) + ". Justifiez la validation (avoir "
            "demandé, prix négocié…) ou corrigez les lignes.",
            code="ecarts",
        )
    invoice.status = "bon_a_payer"
    invoice.approved_at = now()
    invoice.approved_by = ctx.user_id
    invoice.approval_note = (data.note or "").strip() or None
    db.commit()
    return read(db, invoice)


def cancel(db: Session, invoice_id: int) -> SupplierInvoiceRead:
    invoice = _get(db, invoice_id, for_update=True)
    if invoice.status == "annulee" or invoice.paid_amount > 0:
        raise Conflict(
            "Impossible d'annuler : facture déjà annulée ou partiellement payée",
            code="statut_incompatible",
        )
    invoice.status = "annulee"
    db.commit()
    return read(db, invoice)


def pay(db: Session, invoice_id: int, data: SupplierPaymentIn) -> SupplierInvoiceRead:
    invoice = _get(db, invoice_id, for_update=True)
    if invoice.status != "bon_a_payer":
        raise Conflict("Seule une facture « bon à payer » se paie", code="statut_incompatible")
    if data.amount > invoice.total_ttc - invoice.paid_amount:
        raise Invalid(
            f"{data.amount} € dépasse le reste à payer ({invoice.total_ttc - invoice.paid_amount} €)"  # noqa: E501
        )
    db.add(
        SupplierPayment(
            supplier_invoice_id=invoice.id,
            paid_on=data.paid_on,
            amount=data.amount,
            method=data.method,
            reference=data.reference,
        )  # fmt: skip
    )
    invoice.paid_amount += data.amount
    db.commit()
    return read(db, invoice)


def due_soon(db: Session, until: date) -> list[SupplierInvoice]:
    return list(
        db.scalars(
            select(SupplierInvoice).where(
                SupplierInvoice.status == "bon_a_payer",
                SupplierInvoice.total_ttc > SupplierInvoice.paid_amount,
                SupplierInvoice.due_date <= until,
            )
        )
    )
