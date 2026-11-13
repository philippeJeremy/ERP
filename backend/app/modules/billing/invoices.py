"""Factures et avoirs client.

Cycle : brouillon (modifiable, supprimable) → émise (numéro définitif, inaltérable).
Une facture se prépare depuis des bons de livraison (une par BL, ou une
récapitulative par client) ou se saisit librement (prestations).
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.errors import Conflict, NotFound
from app.modules.billing.common import (
    ZERO,
    Invalid,
    due_date,
    get_settings,
    line_total,
    money,
    now,
)
from app.modules.billing.models import (
    Allocation,
    Invoice,
    InvoiceDelivery,
    InvoiceLine,
    Payment,
)
from app.modules.billing.schemas import (
    AllocationRead,
    CreditNoteIn,
    CustomerToBill,
    DeliveryToBill,
    DocRef,
    FromDeliveries,
    InvoiceCreate,
    InvoiceLineRead,
    InvoiceListItem,
    InvoicePage,
    InvoiceRead,
    InvoiceUpdate,
    LineIn,
    VatRow,
)
from app.modules.catalog import public as catalog
from app.modules.org import public as org
from app.modules.partners import public as partners
from app.modules.sales import public as sales

KIND_LABEL = {"facture": "la facture", "avoir": "l'avoir"}


# --- Calculs ----------------------------------------------------------------------------


def eco_total(line: InvoiceLine) -> Decimal:
    return money(line.quantity * line.eco_fee)


def vat_rows(invoice: Invoice) -> list[VatRow]:
    bases: dict[Decimal, Decimal] = {}
    for line in invoice.lines:
        bases[line.vat_rate] = bases.get(line.vat_rate, ZERO) + line.line_total + eco_total(line)
    return [VatRow(rate=r, base=b, vat=money(b * r / 100)) for r, b in sorted(bases.items())]


def recompute(invoice: Invoice) -> None:
    rows = vat_rows(invoice)
    invoice.total_ht = sum((r.base for r in rows), ZERO)
    invoice.total_eco = sum((eco_total(x) for x in invoice.lines), ZERO)
    invoice.total_vat = sum((r.vat for r in rows), ZERO)
    invoice.total_ttc = invoice.total_ht + invoice.total_vat


def balance(invoice: Invoice) -> Decimal:
    return invoice.total_ttc - invoice.paid_amount


def days_late(invoice: Invoice, today: date | None = None) -> int:
    today = today or date.today()
    if invoice.kind != "facture" or invoice.status != "emise" or balance(invoice) <= 0:
        return 0
    if invoice.due_date is None or invoice.due_date >= today:
        return 0
    return (today - invoice.due_date).days


def payment_status(invoice: Invoice) -> str:
    if invoice.status == "brouillon":
        return "brouillon"
    if balance(invoice) <= 0:
        return "payee"
    if days_late(invoice) > 0:
        return "en_retard"
    return "partielle" if invoice.paid_amount > 0 else "a_payer"


# --- Lecture ----------------------------------------------------------------------------


def get(db: Session, invoice_id: int, *, for_update: bool = False) -> Invoice:
    query = select(Invoice).where(Invoice.id == invoice_id)
    if for_update:
        query = query.with_for_update(of=Invoice)
    invoice = db.scalar(query)
    if invoice is None:
        raise NotFound("Facture introuvable")
    return invoice


def _customer_name(db: Session, invoice: Invoice) -> tuple[str, str]:
    if invoice.customer_name:
        return invoice.customer_code or "", invoice.customer_name
    terms = partners.customer_terms(db, invoice.customer_id)
    return terms.code, terms.name


def allocations_of(db: Session, invoice: Invoice) -> list[AllocationRead]:
    """Affectations reçues (facture) ou consommées (avoir)."""
    if invoice.kind == "facture":
        rows = list(db.scalars(select(Allocation).where(Allocation.invoice_id == invoice.id)))
    else:
        rows = list(db.scalars(select(Allocation).where(Allocation.credit_note_id == invoice.id)))
    return describe_allocations(db, rows)


def describe_allocations(db: Session, rows: list[Allocation]) -> list[AllocationRead]:
    payment_ids = {x.payment_id for x in rows if x.payment_id}
    invoice_ids = {x.invoice_id for x in rows} | {
        x.credit_note_id for x in rows if x.credit_note_id
    }
    payments = (
        dict(
            db.execute(select(Payment.id, Payment.number).where(Payment.id.in_(payment_ids))).all()
        )
        if payment_ids
        else {}
    )
    numbers = (
        dict(
            db.execute(select(Invoice.id, Invoice.number).where(Invoice.id.in_(invoice_ids))).all()
        )
        if invoice_ids
        else {}
    )
    return [
        AllocationRead(
            id=x.id,
            amount=x.amount,
            allocated_on=x.allocated_on,
            source="reglement" if x.payment_id else "avoir",
            source_id=x.payment_id or x.credit_note_id,
            source_number=payments.get(x.payment_id)
            if x.payment_id
            else numbers.get(x.credit_note_id) or "",
            invoice_id=x.invoice_id,
            invoice_number=numbers.get(x.invoice_id),
        )  # fmt: skip
        for x in sorted(rows, key=lambda r: r.id)
    ]


def _credited(db: Session, line_ids: set[int]) -> dict[int, Decimal]:
    """Quantités déjà reprises par des avoirs (brouillons compris), par ligne d'origine."""
    if not line_ids:
        return {}
    rows = db.execute(
        select(InvoiceLine.original_line_id, func.sum(InvoiceLine.quantity))
        .where(InvoiceLine.original_line_id.in_(line_ids))
        .group_by(InvoiceLine.original_line_id)
    )
    return {a: q for a, q in rows}


def read(db: Session, invoice: Invoice) -> InvoiceRead:
    code, name = _customer_name(db, invoice)
    credited = (
        _credited(db, {x.id for x in invoice.lines})
        if invoice.kind == "facture" and invoice.status == "emise"
        else {}
    )
    lines = []
    for x in invoice.lines:
        item = InvoiceLineRead.model_validate(x)
        item.eco_total = eco_total(x)
        if invoice.kind == "facture" and invoice.status == "emise":
            item.creditable_qty = x.quantity - credited.get(x.id, ZERO)
        lines.append(item)
    original = None
    if invoice.original_id:
        original = DocRef(id=invoice.original_id, number=get(db, invoice.original_id).number)
    notes = [
        DocRef(id=i, number=n)
        for i, n in db.execute(
            select(Invoice.id, Invoice.number).where(Invoice.original_id == invoice.id)
        ).all()
    ]
    delivery_ids = set(
        db.scalars(
            select(InvoiceDelivery.delivery_id).where(InvoiceDelivery.invoice_id == invoice.id)
        )
    )
    numbers = {x.delivery_id: x.delivery_number for x in invoice.lines if x.delivery_id}
    terms = (
        partners.customer_terms(db, invoice.customer_id) if invoice.status == "brouillon" else None
    )
    return InvoiceRead(
        id=invoice.id, number=invoice.number, kind=invoice.kind, status=invoice.status,
        customer_id=invoice.customer_id, customer_code=code, customer_name=name,
        customer_address=invoice.customer_address
        or ("\n".join(terms.billing_address) if terms else None),
        customer_vat=invoice.customer_vat or (terms.vat_number if terms else None),
        customer_siren=invoice.customer_siren
        or ((terms.siret or "")[:9] or None if terms else None),
        customer_kind=invoice.customer_kind or (terms.kind if terms else "pro"),
        issue_date=invoice.issue_date, due_date=invoice.due_date,
        delivery_date=invoice.delivery_date,
        payment_terms=invoice.payment_terms or (terms.payment_terms if terms else None),
        customer_reference=invoice.customer_reference, note=invoice.note,
        total_ht=invoice.total_ht, total_eco=invoice.total_eco, total_vat=invoice.total_vat,
        total_ttc=invoice.total_ttc, vat=vat_rows(invoice), paid_amount=invoice.paid_amount,
        balance=balance(invoice), payment_status=payment_status(invoice),
        days_late=days_late(invoice), original=original, credit_notes=notes,
        deliveries=[DocRef(id=i, number=numbers.get(i)) for i in sorted(delivery_ids)],
        allocations=allocations_of(db, invoice), reminder_count=invoice.reminder_count,
        last_reminder_at=invoice.last_reminder_at, issued_at=invoice.issued_at,
        sent_at=invoice.sent_at,
        lines=lines, version=invoice.version, created_at=invoice.created_at,
    )  # fmt: skip


def get_invoice(db: Session, invoice_id: int) -> InvoiceRead:
    return read(db, get(db, invoice_id))


def list_item(db: Session, invoice: Invoice, names: dict[int, tuple[str, str]]) -> InvoiceListItem:
    return InvoiceListItem(
        id=invoice.id, number=invoice.number, kind=invoice.kind, status=invoice.status,
        customer_id=invoice.customer_id,
        customer_name=invoice.customer_name or names.get(invoice.customer_id, ("", ""))[1],
        issue_date=invoice.issue_date, due_date=invoice.due_date, total_ht=invoice.total_ht,
        total_ttc=invoice.total_ttc, balance=balance(invoice),
        payment_status=payment_status(invoice), days_late=days_late(invoice),
    )  # fmt: skip


def list_invoices(
    db: Session,
    *,
    kind: str | None,
    status: str | None,
    payment: str | None,
    customer_id: int | None,
    q: str | None,
    limit: int,
    offset: int,
) -> InvoicePage:
    query = select(Invoice)
    if kind:
        query = query.where(Invoice.kind == kind)
    if status:
        query = query.where(Invoice.status == status)
    if customer_id is not None:
        query = query.where(Invoice.customer_id == customer_id)
    open_balance = Invoice.total_ttc > Invoice.paid_amount
    if payment == "a_payer":
        query = query.where(Invoice.status == "emise", open_balance)
    elif payment == "en_retard":
        query = query.where(
            Invoice.status == "emise", Invoice.kind == "facture", open_balance,
            Invoice.due_date < date.today(),
        )  # fmt: skip
    elif payment == "payee":
        query = query.where(Invoice.status == "emise", ~open_balance)
    q = (q or "").strip()
    if q:
        ids = partners.search_partner_ids(db, q)
        condition = Invoice.number.ilike(f"%{q}%") | Invoice.customer_name.ilike(f"%{q}%")
        if ids:
            condition = condition | Invoice.customer_id.in_(ids)
        query = query.where(condition)
    sub = query.subquery()
    total, total_ttc, total_balance = db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(sub.c.total_ttc), 0),
            func.coalesce(func.sum(sub.c.total_ttc - sub.c.paid_amount), 0),
        )
    ).one()
    rows = list(
        db.scalars(
            query.order_by(Invoice.issue_date.desc().nulls_first(), Invoice.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    names = partners.partner_names(db, {x.customer_id for x in rows if not x.customer_name})
    return InvoicePage(
        items=[list_item(db, x, names) for x in rows],
        total=total,
        total_ttc=Decimal(total_ttc),
        total_balance=Decimal(total_balance),
    )


# --- À facturer -------------------------------------------------------------------------


def invoiced_delivery_ids():
    return select(InvoiceDelivery.delivery_id)


def _delivery_ht(d: sales.DeliveryToInvoice) -> Decimal:
    return sum(
        (
            line_total(x.quantity, x.unit_price, x.discount_pct) + money(x.quantity * x.eco_fee)
            for x in d.lines
        ),
        ZERO,
    )


def _delivery_ttc(d: sales.DeliveryToInvoice) -> Decimal:
    return sum(
        (
            (line_total(x.quantity, x.unit_price, x.discount_pct) + money(x.quantity * x.eco_fee))
            * (1 + x.vat_rate / 100)
            for x in d.lines
        ),
        ZERO,
    )


def uninvoiced_ttc(db: Session, customer_id: int) -> Decimal:
    deliveries = sales.uninvoiced_deliveries(db, invoiced_delivery_ids(), customer_id)
    return money(sum((_delivery_ttc(d) for d in deliveries), ZERO))


def to_bill(db: Session, customer_id: int | None) -> list[CustomerToBill]:
    deliveries = sales.uninvoiced_deliveries(db, invoiced_delivery_ids(), customer_id)
    groups: dict[int, list] = {}
    for d in deliveries:
        groups.setdefault(d.customer_id, []).append(d)
    names = partners.partner_names(db, set(groups))
    result = []
    for cid, items in groups.items():
        rows = [
            DeliveryToBill(
                id=d.id,
                number=d.number,
                delivered_on=d.delivered_on,
                order_id=d.order_id,
                order_number=d.order_number,
                customer_reference=d.customer_reference,
                total_ht=_delivery_ht(d),
            )  # fmt: skip
            for d in items
        ]
        result.append(
            CustomerToBill(
                customer_id=cid,
                customer_code=names[cid][0],
                customer_name=names[cid][1],
                deliveries=rows,
                total_ht=sum((r.total_ht for r in rows), ZERO),
            )  # fmt: skip
        )
    return sorted(result, key=lambda x: x.customer_name.lower())


# --- Brouillons -------------------------------------------------------------------------


def _draft(db: Session, invoice_id: int, action: str = "modifier") -> Invoice:
    invoice = get(db, invoice_id, for_update=True)
    if invoice.status != "brouillon":
        raise Conflict(
            f"Impossible de {action} : {KIND_LABEL[invoice.kind]} {invoice.number} est émis(e). "
            "Une facture émise ne se modifie plus : faites un avoir.",
            code="statut_incompatible",
        )
    return invoice


def _new_line(invoice: Invoice, **values) -> InvoiceLine:
    line = InvoiceLine(line_no=max((x.line_no for x in invoice.lines), default=0) + 1, **values)
    line.line_total = line_total(line.quantity, line.unit_price, line.discount_pct)
    invoice.lines.append(line)
    return line


def from_deliveries(db: Session, ctx: RequestContext, data: FromDeliveries) -> list[InvoiceRead]:
    ids = set(data.delivery_ids)
    already = set(
        db.scalars(select(InvoiceDelivery.delivery_id).where(InvoiceDelivery.delivery_id.in_(ids)))
    )
    if already:
        raise Conflict("Un de ces bons de livraison est déjà facturé", code="deja_facture")
    deliveries = sales.deliveries_by_ids(db, ids)
    if len(deliveries) != len(ids):
        raise NotFound("Bon de livraison introuvable")
    groups: list[list[sales.DeliveryToInvoice]] = []
    if data.grouping == "par_bl":
        groups = [[d] for d in deliveries]
    else:
        by_customer: dict[int, list] = {}
        for d in deliveries:
            by_customer.setdefault(d.customer_id, []).append(d)
        groups = list(by_customer.values())
    briefs = catalog.article_briefs(
        db, [x.article_id for d in deliveries for x in d.lines if x.article_id]
    )
    vat_default = get_settings(db).default_vat_rate
    invoices = []
    for group in groups:
        partners.get_customer(db, group[0].customer_id)
        refs = sorted({d.customer_reference for d in group if d.customer_reference})
        invoice = Invoice(
            kind="facture",
            customer_id=group[0].customer_id,
            delivery_date=max(d.delivered_on for d in group),
            customer_reference=", ".join(refs)[:100] or None,
        )
        db.add(invoice)
        for d in group:
            for x in d.lines:
                brief = briefs.get(x.article_id) if x.article_id else None
                _new_line(
                    invoice,
                    delivery_id=d.id, delivery_number=d.number, order_line_id=x.order_line_id,
                    article_id=x.article_id, article_code=brief.code if brief else None,
                    ean=brief.ean if brief else None, designation=x.designation,
                    quantity=x.quantity, unit_price=x.unit_price, discount_pct=x.discount_pct,
                    eco_fee=x.eco_fee, vat_rate=x.vat_rate if x.vat_rate is not None else vat_default,  # noqa: E501
                )  # fmt: skip
        recompute(invoice)
        db.flush()
        for d in group:
            db.add(InvoiceDelivery(invoice_id=invoice.id, delivery_id=d.id))
        db.flush()
        invoices.append(invoice)
    if data.issue:
        for invoice in invoices:
            _issue(db, ctx, invoice)
    db.commit()
    return [read(db, x) for x in invoices]


def create(db: Session, data: InvoiceCreate) -> InvoiceRead:
    partners.get_customer(db, data.customer_id)
    invoice = Invoice(kind="facture", customer_id=data.customer_id)
    db.add(invoice)
    db.commit()
    return read(db, invoice)


def update(db: Session, invoice_id: int, data: InvoiceUpdate) -> InvoiceRead:
    invoice = _draft(db, invoice_id)
    if data.version != invoice.version:
        raise Conflict("La facture a été modifiée entre-temps", code="modifie_entre_temps")
    for field, value in data.model_dump(exclude_unset=True, exclude={"version"}).items():
        setattr(invoice, field, value)
    invoice.updated_at = now()
    db.commit()
    return read(db, invoice)


def _fill(db: Session, line: InvoiceLine, data: LineIn) -> None:
    if data.article_id is not None:
        article = catalog.article_brief(catalog.get_article(db, data.article_id))
        line.article_id, line.article_code, line.ean = article.id, article.code, article.ean
    else:
        line.article_id = line.article_code = line.ean = None
    line.designation = data.designation
    line.quantity = data.quantity
    line.unit_price = data.unit_price
    line.discount_pct = data.discount_pct
    line.eco_fee = data.eco_fee
    line.vat_rate = (
        data.vat_rate if data.vat_rate is not None else get_settings(db).default_vat_rate
    )
    line.line_total = line_total(line.quantity, line.unit_price, line.discount_pct)


def add_line(db: Session, invoice_id: int, data: LineIn) -> InvoiceRead:
    invoice = _draft(db, invoice_id)
    line = InvoiceLine(line_no=max((x.line_no for x in invoice.lines), default=0) + 1)
    _fill(db, line, data)
    invoice.lines.append(line)
    recompute(invoice)
    invoice.updated_at = now()
    db.commit()
    return read(db, invoice)


def update_line(db: Session, invoice_id: int, line_id: int, data: LineIn) -> InvoiceRead:
    invoice = _draft(db, invoice_id)
    line = next((x for x in invoice.lines if x.id == line_id), None)
    if line is None:
        raise NotFound("Ligne introuvable")
    if line.delivery_id or line.original_line_id:
        raise Invalid(
            "Cette ligne vient d'un bon de livraison ou d'une facture : supprimez-la plutôt "
            "que de la modifier."
        )
    _fill(db, line, data)
    recompute(invoice)
    invoice.updated_at = now()
    db.commit()
    return read(db, invoice)


def delete_line(db: Session, invoice_id: int, line_id: int) -> InvoiceRead:
    invoice = _draft(db, invoice_id)
    line = next((x for x in invoice.lines if x.id == line_id), None)
    if line is None:
        raise NotFound("Ligne introuvable")
    invoice.lines.remove(line)
    db.flush()
    if line.delivery_id and not any(x.delivery_id == line.delivery_id for x in invoice.lines):
        # Plus aucune ligne de ce BL : il redevient « à facturer ».
        link = db.scalar(
            select(InvoiceDelivery).where(
                InvoiceDelivery.invoice_id == invoice.id,
                InvoiceDelivery.delivery_id == line.delivery_id,
            )
        )
        if link is not None:
            db.delete(link)
    recompute(invoice)
    invoice.updated_at = now()
    db.commit()
    return read(db, invoice)


def delete(db: Session, invoice_id: int) -> None:
    invoice = _draft(db, invoice_id, "supprimer")
    db.delete(invoice)
    db.commit()


# --- Émission ---------------------------------------------------------------------------


def _issue(db: Session, ctx: RequestContext, invoice: Invoice) -> None:
    if not invoice.lines:
        raise Invalid("La facture n'a aucune ligne")
    if invoice.total_ttc <= 0:
        raise Invalid("Le montant doit être positif")
    company = org.get_company(db, invoice.company_id)
    missing = [
        label
        for label, value in (
            ("SIREN", company.siren),
            ("adresse", company.address_line1),
            ("forme juridique", company.legal_form),
        )  # fmt: skip
        if not value
    ]
    if missing:
        raise Invalid(
            "Mentions légales incomplètes sur la fiche société (" + ", ".join(missing) + ") : "
            "complétez-les dans Administration → Sociétés avant d'émettre."
        )
    terms = partners.customer_terms(db, invoice.customer_id)
    settings = get_settings(db)
    today = date.today()
    invoice.number = org.next_number(db, "invoice" if invoice.kind == "facture" else "credit_note")
    invoice.issue_date = today
    if invoice.kind == "facture":
        days = (
            terms.payment_days if terms.payment_days is not None else settings.default_payment_days
        )
        invoice.due_date = due_date(today, days, terms.payment_end_of_month)
    else:
        invoice.due_date = today
    invoice.customer_code = terms.code
    invoice.customer_name = terms.name
    invoice.customer_address = "\n".join(terms.billing_address) or None
    invoice.customer_siren = (terms.siret or "")[:9] or None
    invoice.customer_vat = terms.vat_number
    invoice.customer_kind = terms.kind
    invoice.payment_terms = terms.payment_terms
    invoice.issued_at = now()
    invoice.issued_by = ctx.user_id
    invoice.status = "emise"
    db.flush()
    if invoice.kind == "avoir" and invoice.original_id:
        # L'avoir vient d'abord en déduction de la facture qu'il corrige.
        original = get(db, invoice.original_id, for_update=True)
        amount = min(balance(original), invoice.total_ttc)
        if amount > 0:
            allocate(db, original, amount, credit_note=invoice)


def issue(db: Session, ctx: RequestContext, invoice_id: int) -> InvoiceRead:
    invoice = _draft(db, invoice_id, "émettre")
    _issue(db, ctx, invoice)
    db.commit()
    return read(db, invoice)


# --- Avoirs -----------------------------------------------------------------------------


def credit_note(db: Session, invoice_id: int, data: CreditNoteIn) -> InvoiceRead:
    original = get(db, invoice_id)
    if original.kind != "facture" or original.status != "emise":
        raise Invalid("Un avoir se fait sur une facture émise")
    credited = _credited(db, {x.id for x in original.lines})
    lines = {x.id: x for x in original.lines}
    wanted: list[tuple[InvoiceLine, Decimal]] = []
    if data.full:
        wanted = [(x, x.quantity - credited.get(x.id, ZERO)) for x in original.lines]
        wanted = [(x, q) for x, q in wanted if q > 0]
    else:
        for item in data.lines:
            line = lines.get(item.line_id)
            if line is None:
                raise NotFound(f"Ligne {item.line_id} introuvable sur la facture")
            left = line.quantity - credited.get(line.id, ZERO)
            if item.quantity > left:
                raise Invalid(
                    f"Ligne {line.line_no} : {item.quantity.normalize():f} demandé(s), "
                    f"{left.normalize():f} encore à reprendre"
                )
            wanted.append((line, item.quantity))
    if not wanted:
        raise Invalid("Rien à reprendre sur cette facture (déjà entièrement avoirée ?)")
    note = Invoice(
        kind="avoir",
        customer_id=original.customer_id,
        original_id=original.id,
        delivery_date=original.delivery_date,
        customer_reference=original.customer_reference,
        note=data.reason,
    )
    db.add(note)
    for line, quantity in wanted:
        new = _new_line(
            note,
            original_line_id=line.id, delivery_number=line.delivery_number,
            article_id=line.article_id, article_code=line.article_code, ean=line.ean,
            designation=line.designation, quantity=quantity, unit_price=line.unit_price,
            discount_pct=line.discount_pct, eco_fee=line.eco_fee, vat_rate=line.vat_rate,
        )  # fmt: skip
        if quantity == line.quantity:
            new.line_total = line.line_total  # exactement le montant facturé
    recompute(note)
    db.commit()
    return read(db, note)


# --- Lettrage (utilisé aussi par les règlements) ---------------------------------------


def allocate(
    db: Session,
    invoice: Invoice,
    amount: Decimal,
    *,
    payment: Payment | None = None,
    credit_note: Invoice | None = None,
) -> Allocation:
    if invoice.kind != "facture" or invoice.status != "emise":
        raise Invalid("On ne lettre que des factures émises")
    if amount > balance(invoice):
        raise Invalid(
            f"{amount} € dépasse le reste dû de la facture {invoice.number} ({balance(invoice)} €)"
        )
    customer = payment.customer_id if payment else credit_note.customer_id  # type: ignore[union-attr]  # noqa: E501
    if customer != invoice.customer_id:
        raise Invalid(f"La facture {invoice.number} est celle d'un autre client")
    if credit_note is not None:
        if credit_note.kind != "avoir" or credit_note.status != "emise":
            raise Invalid("Seul un avoir émis peut être imputé")
        if amount > balance(credit_note):
            raise Invalid(f"Crédit insuffisant sur l'avoir {credit_note.number}")
        credit_note.paid_amount += amount
    allocation = Allocation(
        invoice_id=invoice.id,
        payment_id=payment.id if payment else None,
        credit_note_id=credit_note.id if credit_note else None,
        amount=amount,
        allocated_on=date.today(),
    )
    invoice.paid_amount += amount
    db.add(allocation)
    db.flush()
    return allocation


def apply_credit_note(
    db: Session, credit_note_id: int, invoice_id: int, amount: Decimal
) -> InvoiceRead:
    note = get(db, credit_note_id, for_update=True)
    invoice = get(db, invoice_id, for_update=True)
    allocate(db, invoice, amount, credit_note=note)
    db.commit()
    return read(db, invoice)
