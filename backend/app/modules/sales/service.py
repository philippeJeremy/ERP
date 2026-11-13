"""Règles métier des ventes : tarif, devis, commandes client, livraisons."""

from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, DomainError, NotFound
from app.modules.catalog import public as catalog
from app.modules.inventory import public as inventory
from app.modules.org import public as org
from app.modules.partners import public as partners
from app.modules.sales import repository as repo
from app.modules.sales.models import (
    Delivery,
    DeliveryLine,
    LineFields,
    Price,
    Quote,
    QuoteLine,
    SalesOrder,
    SalesOrderLine,
    SalesSettings,
)
from app.modules.sales.schemas import (
    Accept,
    Confirm,
    Credit,
    CustomerActivity,
    CustomerInfo,
    Deliver,
    DeliveryLineRead,
    DeliveryRead,
    DocRef,
    LineIn,
    LineRead,
    OrderCreate,
    OrderLineRead,
    OrderListItem,
    OrderPage,
    OrderRead,
    OrderUpdate,
    PriceIn,
    PricePage,
    PriceRow,
    Pricing,
    QuoteCreate,
    QuoteListItem,
    QuotePage,
    QuoteRead,
    QuoteUpdate,
    SettingsIn,
    SiteBrief,
    VatRow,
)

CENT = Decimal("0.01")
ZERO = Decimal(0)

# Autres composantes de l'encours, branchées par les modules suivants (la facturation :
# factures impayées, livraisons non encore facturées). Fonction (db, client) → TTC.
OUTSTANDING_SOURCES: list = []


def outstanding(db: Session, customer_id: int, exclude_order_id: int | None = None) -> Decimal:
    total = repo.outstanding(db, customer_id, exclude_order_id=exclude_order_id)
    return total + sum((source(db, customer_id) for source in OUTSTANDING_SOURCES), ZERO)


class Invalid(DomainError):
    status_code = 422
    code = "invalide"


class CreditExceeded(DomainError):
    status_code = 409
    code = "encours_depasse"


def now() -> datetime:
    return datetime.now(UTC)


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def line_total(quantity: Decimal, price: Decimal, discount: Decimal) -> Decimal:
    """Quantité × prix × (1 − remise %), arrondi au centime."""
    return money(quantity * price * (Decimal(100) - discount) / Decimal(100))


QUOTE_LABELS = {
    "brouillon": "en brouillon", "envoye": "envoyé", "accepte": "accepté",
    "refuse": "refusé", "annule": "annulé",
}  # fmt: skip
ORDER_LABELS = {
    "brouillon": "en brouillon", "confirmee": "confirmée", "partielle": "partiellement livrée",
    "livree": "livrée", "cloturee": "clôturée", "annulee": "annulée",
}  # fmt: skip


def _status_error(doc: Quote | SalesOrder, action: str) -> Conflict:
    if isinstance(doc, Quote):
        what = f"le devis est {QUOTE_LABELS.get(doc.status, doc.status)}"
    else:
        what = f"la commande est {ORDER_LABELS.get(doc.status, doc.status)}"
    return Conflict(f"Impossible de {action} : {what}", code="statut_incompatible")


def _check_version(doc: Quote | SalesOrder, version: int) -> None:
    if version != doc.version:
        raise Conflict(
            "Le document a été modifié entre-temps, rechargez-le", code="modifie_entre_temps"
        )


# --- Réglages ---------------------------------------------------------------------------


def get_settings(db: Session) -> SalesSettings:
    return repo.get_settings(db) or SalesSettings(
        quote_validity_days=30, default_vat_rate=Decimal(20)
    )


def save_settings(db: Session, data: SettingsIn) -> SalesSettings:
    settings = repo.get_settings(db)
    if settings is None:
        settings = SalesSettings()
        db.add(settings)
    for field, value in data.model_dump().items():
        setattr(settings, field, value)
    db.commit()
    return settings


# --- Tarif ------------------------------------------------------------------------------


def list_prices(
    db: Session, *, q: str | None, kind: str | None, missing: bool, limit: int, offset: int
) -> PricePage:
    """Le tarif de vente. Sans recherche : les articles qui ont un prix. Avec recherche :
    tous les articles trouvés (pour en tarifer de nouveaux). `missing` : sans prix seulement."""
    ids_query = catalog.article_ids_matching(q, kind)
    article_id = ids_query.selected_columns[0]
    if missing:
        ids_query = ids_query.where(~article_id.in_(repo.priced_article_ids()))
    elif not (q or kind):
        ids_query = ids_query.where(article_id.in_(repo.priced_article_ids()))
    sub = ids_query.subquery()
    total = db.scalar(select(func.count()).select_from(sub)) or 0
    ids = list(db.scalars(select(sub.c[0]).order_by(sub.c[0].desc()).limit(limit).offset(offset)))
    return PricePage(items=_price_rows(db, ids), total=total)


def _price_rows(db: Session, ids: list[int]) -> list[PriceRow]:
    briefs = catalog.article_briefs(db, ids)
    prices = repo.prices_of(db, ids)
    costs = inventory.average_costs(db, set(ids))
    rows = []
    for article_id in ids:
        price = prices.get(article_id)
        cost = costs.get(article_id, ZERO)
        margin = None
        if price is not None and price.sale_price > 0 and cost > 0:
            margin = money((price.sale_price - cost) / price.sale_price * 100)
        rows.append(
            PriceRow(
                article=briefs[article_id],
                kind=catalog.get_article(db, article_id).kind,
                sale_price=price.sale_price if price else None,
                eco_fee=price.eco_fee if price else ZERO,
                average_cost=cost,
                margin_pct=margin,
                updated_at=price.updated_at if price else None,
            )
        )
    return rows


def save_price(db: Session, article_id: int, data: PriceIn) -> PriceRow:
    catalog.get_article(db, article_id)
    price = repo.get_price(db, article_id)
    if price is None:
        price = Price(article_id=article_id)
        db.add(price)
    price.sale_price = data.sale_price
    price.eco_fee = data.eco_fee
    db.commit()
    return _price_rows(db, [article_id])[0]


def delete_price(db: Session, article_id: int) -> None:
    price = repo.get_price(db, article_id)
    if price is not None:
        db.delete(price)
        db.commit()


def pricing(db: Session, customer_id: int, article_id: int, site_id: int | None) -> Pricing:
    terms = partners.customer_terms(db, customer_id)
    article = catalog.get_article(db, article_id)
    price = repo.get_price(db, article_id)
    discount = terms.discount_for(article.kind)
    site = _site_id(db, site_id)
    stock = inventory.availability(db, {article_id}, site)[article_id]
    unit = price.sale_price if price else None
    return Pricing(
        article=catalog.article_brief(article),
        unit_price=unit,
        discount_pct=discount,
        eco_fee=price.eco_fee if price else ZERO,
        vat_rate=get_settings(db).default_vat_rate,
        net_price=money(unit * (100 - discount) / 100) if unit is not None else None,
        on_hand=stock.on_hand,
        available=stock.available,
        average_cost=inventory.average_costs(db, {article_id})[article_id],
    )


# --- Outils communs devis / commande ---------------------------------------------------


def _site_id(db: Session, site_id: int | None) -> int:
    if site_id is not None:
        site = org.get_site(db, site_id)
        if not site.is_active:
            raise Invalid(f"Le dépôt « {site.name} » est désactivé")
        return site.id
    sites = org.list_sites(db, active=True)
    if not sites:
        raise Invalid("Aucun dépôt actif : déclarez d'abord un dépôt (Administration → Dépôts)")
    return sites[0].id


def _active_customer(db: Session, customer_id: int) -> partners.CustomerTerms:
    terms = partners.customer_terms(db, customer_id)
    if not terms.is_active:
        raise Invalid(f"Le client « {terms.name} » est désactivé")
    return terms


def _fill_line(
    db: Session, line: LineFields, data: LineIn, terms: partners.CustomerTerms, vat: Decimal
) -> None:
    """Complète une ligne : ce qui n'est pas saisi vient du tarif et du client."""
    if data.article_id is not None:
        article = catalog.get_article(db, data.article_id)
        if not article.is_active:
            raise Invalid(f"L'article {article.code} est désactivé")
        price = repo.get_price(db, article.id)
        unit_price = data.unit_price if data.unit_price is not None else None
        if unit_price is None:
            if price is None:
                raise Invalid(
                    f"Pas de prix de vente pour {article.code} : renseignez le tarif "
                    "(Ventes → Tarif) ou saisissez un prix."
                )
            unit_price = price.sale_price
        line.article_id = article.id
        line.designation = data.designation or article.designation
        line.unit_price = unit_price
        line.discount_pct = (
            data.discount_pct if data.discount_pct is not None else terms.discount_for(article.kind)
        )
        line.eco_fee = (
            data.eco_fee if data.eco_fee is not None else (price.eco_fee if price else ZERO)
        )
    else:
        if not data.designation:
            raise Invalid("Une ligne libre (sans article) doit avoir une désignation")
        if data.unit_price is None:
            raise Invalid("Une ligne libre doit avoir un prix")
        line.article_id = None
        line.designation = data.designation
        line.unit_price = data.unit_price
        line.discount_pct = data.discount_pct or ZERO
        line.eco_fee = data.eco_fee or ZERO
    line.quantity = data.quantity
    line.vat_rate = data.vat_rate if data.vat_rate is not None else vat
    line.line_total = line_total(line.quantity, line.unit_price, line.discount_pct)


def _eco_total(line: LineFields) -> Decimal:
    return money(line.quantity * line.eco_fee)


def _recompute(doc: Quote | SalesOrder) -> None:
    bases: dict[Decimal, Decimal] = {}
    eco = ZERO
    for line in doc.lines:
        e = _eco_total(line)
        eco += e
        bases[line.vat_rate] = bases.get(line.vat_rate, ZERO) + line.line_total + e
    doc.total_ht = sum(bases.values(), ZERO)
    doc.total_eco = eco
    doc.total_vat = sum((money(b * r / 100) for r, b in bases.items()), ZERO)
    doc.total_ttc = doc.total_ht + doc.total_vat


def _vat_rows(doc: Quote | SalesOrder) -> list[VatRow]:
    bases: dict[Decimal, Decimal] = {}
    for line in doc.lines:
        bases[line.vat_rate] = bases.get(line.vat_rate, ZERO) + line.line_total + _eco_total(line)
    return [VatRow(rate=r, base=b, vat=money(b * r / 100)) for r, b in sorted(bases.items())]


def _next_line_no(doc: Quote | SalesOrder) -> int:
    return max((line.line_no for line in doc.lines), default=0) + 1


def _customer_info(terms: partners.CustomerTerms) -> CustomerInfo:
    return CustomerInfo(
        id=terms.id, code=terms.code, name=terms.name, kind=terms.kind,
        payment_terms=terms.payment_terms, email=terms.email, phone=terms.phone,
        vehicle_registration=terms.vehicle_registration,
        billing_address=terms.billing_address, delivery_address=terms.delivery_address,
    )  # fmt: skip


def _site_brief(db: Session, site_id: int) -> SiteBrief:
    site = org.get_site(db, site_id)
    return SiteBrief(id=site.id, code=site.code, name=site.name)


def _lines_read(db: Session, lines: list) -> tuple[list[dict], Decimal | None]:
    article_ids = {x.article_id for x in lines if x.article_id}
    briefs = catalog.article_briefs(db, list(article_ids))
    costs = inventory.average_costs(db, article_ids)
    out, margin = [], None
    for line in lines:
        cost = costs.get(line.article_id) if line.article_id else None
        line_margin = None
        if cost is not None and cost > 0:
            line_margin = money(line.line_total - line.quantity * cost)
            margin = (margin or ZERO) + line_margin
        out.append(
            dict(
                id=line.id,
                line_no=line.line_no,
                article=briefs.get(line.article_id) if line.article_id else None,
                designation=line.designation,
                quantity=line.quantity,
                unit_price=line.unit_price,
                discount_pct=line.discount_pct,
                eco_fee=line.eco_fee,
                vat_rate=line.vat_rate,
                line_total=line.line_total,
                eco_total=_eco_total(line),
                unit_cost=cost,
                margin=line_margin,
            )  # fmt: skip
        )
    return out, margin


def _doc_fields(db: Session, doc: Quote | SalesOrder, margin: Decimal | None) -> dict:
    return dict(
        id=doc.id, number=doc.number, status=doc.status,
        customer=_customer_info(partners.customer_terms(db, doc.customer_id)),
        site=_site_brief(db, doc.site_id), customer_reference=doc.customer_reference,
        customer_note=doc.customer_note, internal_note=doc.internal_note,
        total_ht=doc.total_ht, total_eco=doc.total_eco, total_vat=doc.total_vat,
        total_ttc=doc.total_ttc, vat=_vat_rows(doc), margin=margin, version=doc.version,
        created_at=doc.created_at, updated_at=doc.updated_at,
    )  # fmt: skip


def _credit(db: Session, customer_id: int) -> Credit:
    terms = partners.customer_terms(db, customer_id)
    return Credit(limit=terms.credit_limit, outstanding=outstanding(db, customer_id))


def _check_credit(db: Session, order: SalesOrder, force: bool) -> None:
    terms = partners.customer_terms(db, order.customer_id)
    if terms.credit_limit is None or force:
        return
    total = outstanding(db, order.customer_id, exclude_order_id=order.id) + order.total_ttc
    if total > terms.credit_limit:
        raise CreditExceeded(
            f"Encours dépassé pour {terms.name} : {money(total)} € TTC avec cette commande, "
            f"pour {terms.credit_limit} € autorisés. Confirmez en connaissance de cause."
        )


# --- Devis -------------------------------------------------------------------------------


def _quote(db: Session, quote_id: int, *, for_update: bool = False) -> Quote:
    quote = repo.get_quote(db, quote_id, for_update=for_update)
    if quote is None:
        raise NotFound("Devis introuvable")
    return quote


def _expired(quote: Quote) -> bool:
    return quote.status in ("brouillon", "envoye") and quote.valid_until < date.today()


def quote_read(db: Session, quote: Quote) -> QuoteRead:
    lines, margin = _lines_read(db, quote.lines)
    order = None
    if quote.order_id:
        order = DocRef(
            id=quote.order_id, number=repo.order_numbers(db, {quote.order_id})[quote.order_id]
        )
    return QuoteRead(
        **_doc_fields(db, quote, margin),
        quote_date=quote.quote_date, valid_until=quote.valid_until, expired=_expired(quote),
        sent_at=quote.sent_at, decided_at=quote.decided_at,
        refusal_reason=quote.refusal_reason, order=order,
        lines=[LineRead(**x) for x in lines],
    )  # fmt: skip


def get_quote(db: Session, quote_id: int) -> QuoteRead:
    return quote_read(db, _quote(db, quote_id))


def _quote_items(db: Session, quotes: list[Quote]) -> list[QuoteListItem]:
    names = partners.partner_names(db, {x.customer_id for x in quotes})
    return [
        QuoteListItem(
            id=x.id,
            number=x.number,
            status=x.status,
            expired=_expired(x),
            customer_id=x.customer_id,
            customer_name=names[x.customer_id][1],
            quote_date=x.quote_date,
            valid_until=x.valid_until,
            total_ht=x.total_ht,
            total_ttc=x.total_ttc,
        )  # fmt: skip
        for x in quotes
    ]


def list_quotes(
    db: Session,
    *,
    status: str | None,
    customer_id: int | None,
    q: str | None,
    limit: int,
    offset: int,
) -> QuotePage:
    q = (q or "").strip() or None
    quotes, total = repo.list_quotes(
        db, status=status, customer_id=customer_id,
        customer_ids=partners.search_partner_ids(db, q) if q else None,
        q=q, limit=limit, offset=offset,
    )  # fmt: skip
    return QuotePage(items=_quote_items(db, quotes), total=total)


def create_quote(db: Session, data: QuoteCreate) -> QuoteRead:
    _active_customer(db, data.customer_id)
    today = date.today()
    quote = Quote(
        number=org.next_number(db, "quote"),
        customer_id=data.customer_id,
        site_id=_site_id(db, data.site_id),
        quote_date=today,
        valid_until=data.valid_until
        or today + timedelta(days=get_settings(db).quote_validity_days),
        customer_reference=data.customer_reference,
        customer_note=data.customer_note,
        internal_note=data.internal_note,
    )
    db.add(quote)
    db.commit()
    return quote_read(db, quote)


def _draft_quote(db: Session, quote_id: int, action: str = "modifier") -> Quote:
    quote = _quote(db, quote_id, for_update=True)
    if quote.status != "brouillon":
        raise _status_error(quote, action)
    return quote


def update_quote(db: Session, quote_id: int, data: QuoteUpdate) -> QuoteRead:
    quote = _draft_quote(db, quote_id)
    _check_version(quote, data.version)
    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    if "site_id" in changes:
        changes["site_id"] = _site_id(db, changes["site_id"])
    if changes.get("valid_until") is None:
        changes.pop("valid_until", None)
    for field, value in changes.items():
        setattr(quote, field, value)
    quote.updated_at = now()
    db.commit()
    return quote_read(db, quote)


def add_quote_line(db: Session, quote_id: int, data: LineIn) -> QuoteRead:
    quote = _draft_quote(db, quote_id)
    terms = partners.customer_terms(db, quote.customer_id)
    line = QuoteLine(line_no=_next_line_no(quote))
    _fill_line(db, line, data, terms, get_settings(db).default_vat_rate)
    quote.lines.append(line)
    _recompute(quote)
    quote.updated_at = now()
    db.commit()
    return quote_read(db, quote)


def update_quote_line(db: Session, quote_id: int, line_id: int, data: LineIn) -> QuoteRead:
    quote = _draft_quote(db, quote_id)
    line = next((x for x in quote.lines if x.id == line_id), None)
    if line is None:
        raise NotFound("Ligne introuvable")
    terms = partners.customer_terms(db, quote.customer_id)
    _fill_line(db, line, data, terms, get_settings(db).default_vat_rate)
    _recompute(quote)
    quote.updated_at = now()
    db.commit()
    return quote_read(db, quote)


def delete_quote_line(db: Session, quote_id: int, line_id: int) -> QuoteRead:
    quote = _draft_quote(db, quote_id)
    line = next((x for x in quote.lines if x.id == line_id), None)
    if line is None:
        raise NotFound("Ligne introuvable")
    quote.lines.remove(line)
    _recompute(quote)
    quote.updated_at = now()
    db.commit()
    return quote_read(db, quote)


def send_quote(db: Session, quote_id: int) -> QuoteRead:
    quote = _draft_quote(db, quote_id, "envoyer")
    if not quote.lines:
        raise Invalid("Le devis n'a aucune ligne")
    quote.status = "envoye"
    quote.sent_at = now()
    db.commit()
    return quote_read(db, quote)


def reopen_quote(db: Session, quote_id: int) -> QuoteRead:
    quote = _quote(db, quote_id, for_update=True)
    if quote.status not in ("envoye", "refuse"):
        raise _status_error(quote, "rouvrir")
    quote.status = "brouillon"
    quote.decided_at = None
    quote.refusal_reason = None
    db.commit()
    return quote_read(db, quote)


def refuse_quote(db: Session, quote_id: int, reason: str) -> QuoteRead:
    quote = _quote(db, quote_id, for_update=True)
    if quote.status not in ("brouillon", "envoye"):
        raise _status_error(quote, "refuser")
    quote.status = "refuse"
    quote.decided_at = now()
    quote.refusal_reason = reason
    db.commit()
    return quote_read(db, quote)


def cancel_quote(db: Session, quote_id: int) -> QuoteRead:
    quote = _quote(db, quote_id, for_update=True)
    if quote.status not in ("brouillon", "envoye"):
        raise _status_error(quote, "annuler")
    quote.status = "annule"
    db.commit()
    return quote_read(db, quote)


def accept_quote(db: Session, quote_id: int, data: Accept) -> OrderRead:
    """Le client dit oui : la commande est créée, confirmée, et le stock réservé."""
    quote = _quote(db, quote_id, for_update=True)
    if quote.status not in ("brouillon", "envoye"):
        raise _status_error(quote, "accepter")
    _check_version(quote, data.version)
    if not quote.lines:
        raise Invalid("Le devis n'a aucune ligne")
    _active_customer(db, quote.customer_id)
    order = SalesOrder(
        number=org.next_number(db, "sales_order"),
        customer_id=quote.customer_id,
        site_id=quote.site_id,
        quote_id=quote.id,
        order_date=date.today(),
        customer_reference=quote.customer_reference,
        customer_note=quote.customer_note,
        internal_note=quote.internal_note,
    )
    for q in quote.lines:
        order.lines.append(
            SalesOrderLine(
                line_no=q.line_no,
                article_id=q.article_id,
                designation=q.designation,
                quantity=q.quantity,
                unit_price=q.unit_price,
                discount_pct=q.discount_pct,
                eco_fee=q.eco_fee,
                vat_rate=q.vat_rate,
                line_total=q.line_total,
            )  # fmt: skip
        )
    _recompute(order)
    db.add(order)
    db.flush()
    _confirm(db, order, data.force)
    quote.status = "accepte"
    quote.decided_at = now()
    quote.order_id = order.id
    db.commit()
    return order_read(db, order)


# --- Commandes ---------------------------------------------------------------------------


def _order(db: Session, order_id: int, *, for_update: bool = False) -> SalesOrder:
    order = repo.get_order(db, order_id, for_update=for_update)
    if order is None:
        raise NotFound("Commande introuvable")
    return order


def _remaining(line: SalesOrderLine) -> Decimal:
    return line.quantity - line.delivered_qty


def _delivery_read(
    db: Session, delivery: Delivery, lines_by_id: dict[int, SalesOrderLine]
) -> DeliveryRead:
    locations = inventory.location_codes(
        db, {x.location_id for x in delivery.lines if x.location_id}
    )
    return DeliveryRead(
        id=delivery.id, number=delivery.number, delivered_on=delivery.delivered_on,
        carrier=delivery.carrier, note=delivery.note, created_at=delivery.created_at,
        lines=[
            DeliveryLineRead(
                order_line_id=x.order_line_id, line_no=lines_by_id[x.order_line_id].line_no,
                designation=lines_by_id[x.order_line_id].designation, quantity=x.quantity,
                location_code=locations.get(x.location_id), dot=x.dot,
            )
            for x in delivery.lines
        ],
    )  # fmt: skip


def order_read(db: Session, order: SalesOrder) -> OrderRead:
    lines, margin = _lines_read(db, order.lines)
    article_ids = {x.article_id for x in order.lines if x.article_id}
    stock = inventory.availability(db, article_ids, order.site_id)
    by_id = {x.id: x for x in order.lines}
    order_lines = []
    for data, line in zip(lines, order.lines, strict=True):
        order_lines.append(
            OrderLineRead(
                **data,
                dot=line.dot,
                delivered_qty=line.delivered_qty,
                remaining_qty=_remaining(line),
                on_hand=stock[line.article_id].on_hand if line.article_id else None,
            )  # fmt: skip
        )
    quote = None
    if order.quote_id:
        quote = DocRef(id=order.quote_id, number=repo.quote_number(db, order.quote_id) or "")
    return OrderRead(
        **_doc_fields(db, order, margin),
        order_date=order.order_date, requested_date=order.requested_date,
        delivery_address=order.delivery_address, confirmed_at=order.confirmed_at,
        closed_at=order.closed_at, cancel_reason=order.cancel_reason, quote=quote,
        credit=_credit(db, order.customer_id), lines=order_lines,
        deliveries=[_delivery_read(db, d, by_id) for d in repo.deliveries_of(db, order.id)],
    )  # fmt: skip


def get_order(db: Session, order_id: int) -> OrderRead:
    return order_read(db, _order(db, order_id))


def _order_items(db: Session, orders: list[SalesOrder]) -> list[OrderListItem]:
    names = partners.partner_names(db, {x.customer_id for x in orders})
    sites = {s.id: s.name for s in org.list_sites(db)}
    return [
        OrderListItem(
            id=x.id,
            number=x.number,
            status=x.status,
            customer_id=x.customer_id,
            customer_name=names[x.customer_id][1],
            site_name=sites.get(x.site_id, ""),
            order_date=x.order_date,
            requested_date=x.requested_date,
            total_ht=x.total_ht,
            total_ttc=x.total_ttc,
        )  # fmt: skip
        for x in orders
    ]


def list_orders(
    db: Session,
    *,
    status: str | None,
    open_only: bool,
    customer_id: int | None,
    q: str | None,
    limit: int,
    offset: int,
) -> OrderPage:
    q = (q or "").strip() or None
    orders, total = repo.list_orders(
        db, status=status, open_only=open_only, customer_id=customer_id,
        customer_ids=partners.search_partner_ids(db, q) if q else None,
        q=q, limit=limit, offset=offset,
    )  # fmt: skip
    return OrderPage(items=_order_items(db, orders), total=total)


def create_order(db: Session, data: OrderCreate) -> OrderRead:
    _active_customer(db, data.customer_id)
    order = SalesOrder(
        number=org.next_number(db, "sales_order"),
        customer_id=data.customer_id,
        site_id=_site_id(db, data.site_id),
        order_date=date.today(),
        requested_date=data.requested_date,
        customer_reference=data.customer_reference,
        customer_note=data.customer_note,
        internal_note=data.internal_note,
    )
    db.add(order)
    db.commit()
    return order_read(db, order)


def _draft_order(db: Session, order_id: int, action: str = "modifier") -> SalesOrder:
    order = _order(db, order_id, for_update=True)
    if order.status != "brouillon":
        raise _status_error(order, action)
    return order


def update_order(db: Session, order_id: int, data: OrderUpdate) -> OrderRead:
    order = _order(db, order_id, for_update=True)
    _check_version(order, data.version)
    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    if order.status != "brouillon":
        # Après confirmation, seules les informations sans effet sur le stock changent.
        if "site_id" in changes and changes["site_id"] != order.site_id:
            raise _status_error(order, "changer de dépôt")
        changes.pop("site_id", None)
        if order.status not in ("confirmee", "partielle"):
            raise _status_error(order, "modifier")
    elif "site_id" in changes:
        changes["site_id"] = _site_id(db, changes["site_id"])
    for field, value in changes.items():
        setattr(order, field, value)
    order.updated_at = now()
    db.commit()
    return order_read(db, order)


def add_order_line(db: Session, order_id: int, data: LineIn) -> OrderRead:
    order = _draft_order(db, order_id)
    terms = partners.customer_terms(db, order.customer_id)
    line = SalesOrderLine(line_no=_next_line_no(order), dot=data.dot)
    _fill_line(db, line, data, terms, get_settings(db).default_vat_rate)
    order.lines.append(line)
    _recompute(order)
    order.updated_at = now()
    db.commit()
    return order_read(db, order)


def update_order_line(db: Session, order_id: int, line_id: int, data: LineIn) -> OrderRead:
    order = _draft_order(db, order_id)
    line = next((x for x in order.lines if x.id == line_id), None)
    if line is None:
        raise NotFound("Ligne introuvable")
    terms = partners.customer_terms(db, order.customer_id)
    _fill_line(db, line, data, terms, get_settings(db).default_vat_rate)
    line.dot = data.dot
    _recompute(order)
    order.updated_at = now()
    db.commit()
    return order_read(db, order)


def delete_order_line(db: Session, order_id: int, line_id: int) -> OrderRead:
    order = _draft_order(db, order_id)
    line = next((x for x in order.lines if x.id == line_id), None)
    if line is None:
        raise NotFound("Ligne introuvable")
    order.lines.remove(line)
    _recompute(order)
    order.updated_at = now()
    db.commit()
    return order_read(db, order)


def delete_order(db: Session, order_id: int) -> None:
    order = _draft_order(db, order_id, "supprimer")
    if order.quote_id:
        raise Invalid("Cette commande vient d'un devis accepté : annulez-la plutôt")
    db.delete(order)
    db.commit()


def _reserve(db: Session, order: SalesOrder) -> None:
    """Réservation = reste à livrer de chaque ligne article (0 = libérée)."""
    for line in order.lines:
        if line.article_id is None:
            continue
        remaining = _remaining(line) if order.status in ("confirmee", "partielle") else ZERO
        inventory.set_reservation(
            db,
            source=f"sales_order_line:{line.id}",
            article_id=line.article_id,
            site_id=order.site_id,
            quantity=remaining,
            reference=order.number,
        )


def _confirm(db: Session, order: SalesOrder, force: bool) -> None:
    if not order.lines:
        raise Invalid("La commande n'a aucune ligne")
    _check_credit(db, order, force)
    terms = partners.customer_terms(db, order.customer_id)
    order.status = "confirmee"
    order.confirmed_at = now()
    order.delivery_address = "\n".join([terms.name, *terms.delivery_address])
    db.flush()
    _reserve(db, order)


def confirm_order(db: Session, order_id: int, data: Confirm) -> OrderRead:
    order = _draft_order(db, order_id, "confirmer")
    _check_version(order, data.version)
    _active_customer(db, order.customer_id)
    _confirm(db, order, data.force)
    db.commit()
    return order_read(db, order)


def reopen_order(db: Session, order_id: int) -> OrderRead:
    """Repasse en brouillon pour modifier : possible tant que rien n'est livré."""
    order = _order(db, order_id, for_update=True)
    if order.status != "confirmee" or any(x.delivered_qty > 0 for x in order.lines):
        raise _status_error(order, "repasser en brouillon")
    order.status = "brouillon"
    order.confirmed_at = None
    _reserve(db, order)  # libère les réservations
    db.commit()
    return order_read(db, order)


def deliver(db: Session, order_id: int, data: Deliver) -> OrderRead:
    """Livraison : sortie de stock (DOT les plus anciens d'abord), bon de livraison."""
    order = _order(db, order_id, for_update=True)
    if order.status not in ("confirmee", "partielle"):
        raise _status_error(order, "livrer")
    lines = {x.id: x for x in order.lines}
    asked: dict[int, Decimal] = {}
    for item in data.lines:
        line = lines.get(item.line_id)
        if line is None:
            raise NotFound(f"Ligne {item.line_id} introuvable dans cette commande")
        asked[line.id] = asked.get(line.id, ZERO) + item.quantity
        if asked[line.id] > _remaining(line):
            raise Invalid(
                f"Ligne {line.line_no} : {asked[line.id].normalize():f} à livrer, "
                f"il n'en reste que {_remaining(line).normalize():f}"
            )
    delivery = Delivery(
        number=org.next_number(db, "delivery"),
        order_id=order.id,
        site_id=order.site_id,
        delivered_on=data.delivered_on,
        carrier=data.carrier,
        note=data.note,
    )
    db.add(delivery)
    db.flush()
    for item in data.lines:
        line = lines[item.line_id]
        if line.article_id is None:
            delivery.lines.append(DeliveryLine(order_line_id=line.id, quantity=item.quantity))
        else:
            lots = inventory.issue_stock(
                db,
                article_id=line.article_id,
                site_id=order.site_id,
                quantity=item.quantity,
                location_id=item.location_id,
                dot=item.dot or line.dot or None,
                source=f"delivery:{delivery.id}",
                reference=delivery.number,
            )
            for lot in lots:
                delivery.lines.append(
                    DeliveryLine(
                        order_line_id=line.id,
                        quantity=lot.quantity,
                        location_id=lot.location_id,
                        dot=lot.dot,
                        unit_cost=lot.unit_cost,
                    )  # fmt: skip
                )
        line.delivered_qty += item.quantity
    order.status = "livree" if all(_remaining(x) <= 0 for x in order.lines) else "partielle"
    if order.status == "livree":
        order.closed_at = now()
    _reserve(db, order)
    db.commit()
    return order_read(db, order)


def close_order(db: Session, order_id: int, reason: str) -> OrderRead:
    """Solde une commande partiellement livrée : le reliquat est abandonné."""
    order = _order(db, order_id, for_update=True)
    if order.status != "partielle":
        raise _status_error(order, "clôturer")
    order.status = "cloturee"
    order.closed_at = now()
    order.cancel_reason = reason
    _reserve(db, order)
    db.commit()
    return order_read(db, order)


def cancel_order(db: Session, order_id: int, reason: str) -> OrderRead:
    order = _order(db, order_id, for_update=True)
    if order.status not in ("brouillon", "confirmee"):
        raise _status_error(order, "annuler")
    order.status = "annulee"
    order.cancel_reason = reason
    _reserve(db, order)
    db.commit()
    return order_read(db, order)


def customer_activity(db: Session, customer_id: int) -> CustomerActivity:
    partners.get_customer(db, customer_id)
    quotes, _ = repo.list_quotes(
        db, status=None, customer_id=customer_id, customer_ids=None, q=None, limit=10, offset=0
    )
    orders, _ = repo.list_orders(
        db, status=None, open_only=False, customer_id=customer_id, customer_ids=None,
        q=None, limit=10, offset=0,
    )  # fmt: skip
    return CustomerActivity(
        credit=_credit(db, customer_id),
        quotes=_quote_items(db, quotes),
        orders=_order_items(db, orders),
    )
