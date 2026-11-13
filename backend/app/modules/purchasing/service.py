"""Règles métier des achats : commandes fournisseur, validation, accusé, réceptions."""

from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.errors import Conflict, DomainError, NotFound
from app.modules.catalog import public as catalog
from app.modules.inventory import public as inventory
from app.modules.org import public as org
from app.modules.partners import public as partners
from app.modules.purchasing import repository as repo
from app.modules.purchasing.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseSettings,
    Reception,
    ReceptionLine,
)
from app.modules.purchasing.schemas import (
    Acknowledge,
    LineIn,
    LineRead,
    OrderCreate,
    OrderListItem,
    OrderPage,
    OrderRead,
    OrderUpdate,
    Receive,
    ReceptionRead,
    SettingsIn,
    SiteBrief,
    SupplierInfo,
)

CENT = Decimal("0.01")
EDITABLE = ("brouillon",)
RECEIVABLE = ("validee", "envoyee", "confirmee", "partielle")


class Invalid(DomainError):
    status_code = 422
    code = "invalide"


def now() -> datetime:
    return datetime.now(UTC)


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def line_total(quantity: Decimal, price: Decimal, discount: Decimal) -> Decimal:
    """Quantité × prix × (1 − remise %), arrondi au centime (arrondi commercial)."""
    return money(quantity * price * (Decimal(100) - discount) / Decimal(100))


def _status_error(order: PurchaseOrder, action: str) -> Conflict:
    labels = {
        "brouillon": "en brouillon", "a_valider": "en attente de validation",
        "validee": "validée", "envoyee": "envoyée", "confirmee": "confirmée",
        "partielle": "partiellement reçue", "recue": "reçue", "cloturee": "clôturée",
        "annulee": "annulée",
    }  # fmt: skip
    return Conflict(
        f"Impossible de {action} : la commande est {labels.get(order.status, order.status)}",
        code="statut_incompatible",
    )


def _get(db: Session, order_id: int, *, for_update: bool = False) -> PurchaseOrder:
    order = repo.get_order(db, order_id, for_update=for_update)
    if order is None:
        raise NotFound("Commande introuvable")
    return order


def _check_version(order: PurchaseOrder, version: int) -> None:
    if version != order.version:
        raise Conflict(
            "La commande a été modifiée entre-temps, rechargez-la", code="modifie_entre_temps"
        )


def _settings(db: Session) -> PurchaseSettings | None:
    return repo.get_settings(db)


# --- Lecture -------------------------------------------------------------------------


def order_read(db: Session, order: PurchaseOrder) -> OrderRead:
    terms = partners.supplier_terms(db, order.partner_id)
    site = org.get_site(db, order.site_id)
    settings = _settings(db)
    warnings: list[str] = []
    if order.status in ("brouillon", "a_valider", "validee"):
        if terms.min_order_amount and order.total_ht < terms.min_order_amount:
            warnings.append(
                f"Minimum de commande non atteint : {terms.min_order_amount:.2f} "
                f"{order.currency} HT"
            )
        if terms.free_shipping_amount:
            missing = terms.free_shipping_amount - order.total_ht
            if missing > 0:
                warnings.append(f"Franco de port : il manque {missing:.2f} {order.currency} HT")
        for line in order.lines:
            if line.article_id:
                offer = catalog.supplier_offer(db, line.article_id, order.partner_id)
                if offer is None:
                    warnings.append(
                        f"Ligne {line.line_no} : article non référencé chez ce fournisseur"
                    )
                elif offer.is_discontinued:
                    warnings.append(f"Ligne {line.line_no} : article arrêté chez ce fournisseur")
    return OrderRead(
        id=order.id,
        number=order.number,
        status=order.status,
        supplier=SupplierInfo(**{k: getattr(terms, k) for k in SupplierInfo.model_fields}),
        site=SiteBrief(id=site.id, code=site.code, name=site.name, city=site.city),
        order_date=order.order_date,
        expected_date=order.expected_date,
        currency=order.currency,
        supplier_reference=order.supplier_reference,
        supplier_note=order.supplier_note,
        internal_note=order.internal_note,
        total_ht=order.total_ht,
        submitted_at=order.submitted_at,
        approved_at=order.approved_at,
        rejection_reason=order.rejection_reason,
        sent_at=order.sent_at,
        confirmed_at=order.confirmed_at,
        closed_at=order.closed_at,
        cancel_reason=order.cancel_reason,
        approval_threshold=settings.approval_threshold if settings else None,
        lines=[LineRead.model_validate(line) for line in order.lines],
        receptions=[ReceptionRead.model_validate(r) for r in repo.receptions_of(db, order.id)],
        warnings=warnings,
        version=order.version,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


def get_order(db: Session, order_id: int) -> OrderRead:
    return order_read(db, _get(db, order_id))


def list_orders(db: Session, *, group, status, partner_id, q, limit, offset) -> OrderPage:
    q = (q or "").strip() or None
    rows, total = repo.search_orders(
        db,
        group=group,
        status=status,
        partner_id=partner_id,
        q=q,
        q_partner_ids=partners.search_partner_ids(db, q) if q else [],
        limit=limit,
        offset=offset,
    )
    names = partners.partner_names(db, {order.partner_id for order, *_ in rows})
    sites = {s.id: s.name for s in org.list_sites(db)}
    items = [
        OrderListItem(
            id=order.id,
            number=order.number,
            status=order.status,
            partner_id=order.partner_id,
            partner_name=names.get(order.partner_id, ("", "?"))[1],
            site_name=sites.get(order.site_id, "?"),
            order_date=order.order_date,
            expected_date=order.expected_date,
            total_ht=order.total_ht,
            line_count=count or 0,
            received_ratio=float(received / qty) if qty else 0.0,
        )
        for order, count, qty, received in rows
    ]
    return OrderPage(items=items, total=total)


# --- Brouillon : en-tête et lignes ----------------------------------------------------


def _site_id(db: Session, site_id: int | None) -> int:
    if site_id is not None:
        site = org.get_site(db, site_id)
        if not site.is_active:
            raise Invalid(f"Le dépôt « {site.name} » est désactivé")
        return site.id
    sites = org.list_sites(db, active=True)
    if not sites:
        raise Invalid(
            "Aucun dépôt actif : déclarez d'abord un lieu de livraison (Administration → Dépôts)"
        )
    return sites[0].id  # le dépôt par défaut est en tête


def create_order(db: Session, data: OrderCreate) -> OrderRead:
    terms = partners.supplier_terms(db, data.partner_id)
    if not terms.is_active:
        raise Invalid(f"Le fournisseur « {terms.name} » est désactivé")
    order = PurchaseOrder(
        partner_id=terms.id,
        site_id=_site_id(db, data.site_id),
        expected_date=data.expected_date,
        currency=terms.currency,
        supplier_note=data.supplier_note,
        internal_note=data.internal_note,
    )
    db.add(order)
    db.commit()
    return order_read(db, order)


def update_order(db: Session, order_id: int, data: OrderUpdate) -> OrderRead:
    order = _get(db, order_id, for_update=True)
    _check_version(order, data.version)
    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    # En brouillon tout se modifie ; après, seulement ce qui n'engage pas le fournisseur.
    later = {"supplier_reference", "internal_note", "expected_date"}
    if order.status not in EDITABLE and set(changes) - later:
        raise _status_error(order, "modifier le dépôt ou la note fournisseur")
    if order.status in ("recue", "cloturee", "annulee") and set(changes) - {"internal_note"}:
        raise _status_error(order, "modifier la commande")
    if "site_id" in changes:
        changes["site_id"] = _site_id(db, changes["site_id"])
    for field, value in changes.items():
        setattr(order, field, value)
    db.commit()
    return order_read(db, order)


def _recompute(order: PurchaseOrder) -> None:
    order.total_ht = money(sum((line.line_total for line in order.lines), Decimal(0)))
    order.updated_at = now()  # la version change : les autres écrans verront la modification


def _fill_line(db: Session, order: PurchaseOrder, line: PurchaseOrderLine, data: LineIn) -> None:
    price, ref, designation = data.unit_price, data.supplier_ref, data.designation
    if data.article_id is not None:
        catalog.get_article(db, data.article_id)  # existe ?
        offer = catalog.supplier_offer(db, data.article_id, order.partner_id)
        if offer is not None:
            price = price if price is not None else offer.purchase_price
            ref = ref or offer.supplier_ref
        designation = designation or catalog.article_label(db, data.article_id)
    if not designation:
        raise Invalid("Désignation obligatoire pour une ligne sans article")
    if price is None:
        raise Invalid("Prix inconnu pour ce fournisseur : indiquez le prix d'achat")
    line.article_id = data.article_id
    line.supplier_ref = ref
    line.designation = designation
    line.quantity = data.quantity
    line.unit_price = price
    line.discount_pct = data.discount_pct
    line.line_total = line_total(data.quantity, price, data.discount_pct)


def add_line(db: Session, order_id: int, data: LineIn) -> OrderRead:
    order = _get(db, order_id, for_update=True)
    if order.status not in EDITABLE:
        raise _status_error(order, "ajouter une ligne")
    line = PurchaseOrderLine(line_no=max((x.line_no for x in order.lines), default=0) + 1)
    _fill_line(db, order, line, data)
    order.lines.append(line)
    _recompute(order)
    db.commit()
    return order_read(db, order)


def update_line(db: Session, order_id: int, line_id: int, data: LineIn) -> OrderRead:
    order = _get(db, order_id, for_update=True)
    if order.status not in EDITABLE:
        raise _status_error(order, "modifier une ligne")
    line = next((x for x in order.lines if x.id == line_id), None)
    if line is None:
        raise NotFound("Ligne introuvable")
    _fill_line(db, order, line, data)
    _recompute(order)
    db.commit()
    return order_read(db, order)


def delete_line(db: Session, order_id: int, line_id: int) -> OrderRead:
    order = _get(db, order_id, for_update=True)
    if order.status not in EDITABLE:
        raise _status_error(order, "supprimer une ligne")
    line = next((x for x in order.lines if x.id == line_id), None)
    if line is None:
        raise NotFound("Ligne introuvable")
    order.lines.remove(line)
    for i, x in enumerate(order.lines, start=1):  # renumérotation 1, 2, 3…
        x.line_no = -i  # étape intermédiaire : évite un doublon temporaire (unicité)
    db.flush()
    for x in order.lines:
        x.line_no = -x.line_no
    _recompute(order)
    db.commit()
    return order_read(db, order)


def delete_order(db: Session, order_id: int) -> None:
    order = _get(db, order_id, for_update=True)
    if order.status != "brouillon":
        raise _status_error(order, "supprimer la commande (annulez-la)")
    db.delete(order)
    db.commit()


# --- Validation ----------------------------------------------------------------------


def _number(db: Session, order: PurchaseOrder) -> None:
    order.number = org.next_number(db, "purchase_order")
    order.order_date = date.today()


def submit(db: Session, ctx: RequestContext, order_id: int, version: int) -> OrderRead:
    """« Valider » : au-delà du seuil, il faut le droit purchasing:approve, sinon la
    commande attend un valideur. Le numéro est attribué à la validation effective."""
    order = _get(db, order_id, for_update=True)
    _check_version(order, version)
    if order.status != "brouillon":
        raise _status_error(order, "valider la commande")
    if not order.lines:
        raise Invalid("La commande n'a aucune ligne")
    settings = _settings(db)
    threshold = settings.approval_threshold if settings else None
    order.submitted_by, order.submitted_at = ctx.user_id, now()
    order.rejection_reason = None
    if threshold is not None and order.total_ht > threshold and not ctx.has("purchasing:approve"):
        order.status = "a_valider"
    else:
        order.status = "validee"
        if threshold is not None and order.total_ht > threshold:
            order.approved_by, order.approved_at = ctx.user_id, now()
        _number(db, order)
    db.commit()
    return order_read(db, order)


def approve(db: Session, ctx: RequestContext, order_id: int, version: int) -> OrderRead:
    order = _get(db, order_id, for_update=True)
    _check_version(order, version)
    if order.status != "a_valider":
        raise _status_error(order, "approuver la commande")
    if order.submitted_by == ctx.user_id and not ctx.is_superuser:
        # Le principe des « quatre yeux » : on ne valide pas sa propre demande.
        raise Conflict("Une autre personne doit approuver votre commande", code="auto_validation")
    order.status = "validee"
    order.approved_by, order.approved_at = ctx.user_id, now()
    _number(db, order)
    db.commit()
    return order_read(db, order)


def reject(db: Session, order_id: int, reason: str) -> OrderRead:
    order = _get(db, order_id, for_update=True)
    if order.status != "a_valider":
        raise _status_error(order, "refuser la commande")
    order.status = "brouillon"
    order.rejection_reason = reason
    db.commit()
    return order_read(db, order)


# --- Envoi, accusé, réception, clôture -------------------------------------------------


def mark_sent(db: Session, order_id: int) -> OrderRead:
    order = _get(db, order_id, for_update=True)
    if order.status != "validee":
        raise _status_error(order, "marquer la commande envoyée")
    order.status = "envoyee"
    order.sent_at = now()
    db.commit()
    return order_read(db, order)


def acknowledge(db: Session, order_id: int, data: Acknowledge) -> OrderRead:
    """Accusé de commande du fournisseur : quantités et dates qu'il s'engage à livrer."""
    order = _get(db, order_id, for_update=True)
    if order.status not in ("envoyee", "confirmee", "partielle"):
        raise _status_error(order, "saisir l'accusé")
    lines = {x.id: x for x in order.lines}
    for ack in data.lines:
        line = lines.get(ack.line_id)
        if line is None:
            raise NotFound(f"Ligne {ack.line_id} introuvable dans cette commande")
        line.confirmed_qty = ack.confirmed_qty
        line.confirmed_date = ack.confirmed_date
    if data.supplier_reference is not None:
        order.supplier_reference = data.supplier_reference or None
    if order.status == "envoyee":
        order.status = "confirmee"
    order.confirmed_at = now()
    order.updated_at = now()
    db.commit()
    return order_read(db, order)


def receive(db: Session, order_id: int, data: Receive) -> OrderRead:
    """Enregistre une livraison (partielle ou totale), avec le n° du bon de livraison."""
    order = _get(db, order_id, for_update=True)
    if order.status not in RECEIVABLE:
        raise _status_error(order, "réceptionner")
    lines = {x.id: x for x in order.lines}
    received = [r for r in data.lines if r.quantity > 0]
    if not received:
        raise Invalid("Indiquez au moins une quantité reçue")
    reception = Reception(
        number=org.next_number(db, "reception"),
        order_id=order.id,
        site_id=order.site_id,
        received_on=data.received_on,
        delivery_note=data.delivery_note,
        note=data.note,
    )
    db.add(reception)
    db.flush()  # l'id de la réception sert de référence aux mouvements de stock
    for item in received:
        line = lines.get(item.line_id)
        if line is None:
            raise NotFound(f"Ligne {item.line_id} introuvable dans cette commande")
        remaining = line.quantity - line.received_qty
        if item.quantity > remaining:
            raise Invalid(
                f"Ligne {line.line_no} : {item.quantity:g} reçus pour un reste à recevoir de "
                f"{remaining:g}. Une livraison en trop se traite avec le fournisseur (retour)."
            )
        line.received_qty += item.quantity
        location_id = None
        if line.article_id is not None:
            # Entrée en stock au coût d'achat NET (remise déduite) : c'est lui qui alimente
            # le coût moyen pondéré. Une ligne libre (sans article) n'entre pas en stock.
            location_id = inventory.receive_stock(
                db,
                article_id=line.article_id,
                site_id=order.site_id,
                location_id=item.location_id,
                dot=item.dot,
                quantity=item.quantity,
                unit_cost=line.line_total / line.quantity,
                source=f"reception:{reception.id}",
                reference=reception.number,
            )
        reception.lines.append(
            ReceptionLine(
                order_line_id=line.id,
                quantity=item.quantity,
                location_id=location_id,
                dot=item.dot,
            )
        )
    complete = all(x.received_qty >= x.quantity for x in order.lines)
    order.status = "recue" if complete else "partielle"
    order.updated_at = now()
    db.commit()
    return order_read(db, order)


def close(db: Session, order_id: int, reason: str) -> OrderRead:
    """Clôture : on n'attend plus le reliquat (rupture définitive chez le fournisseur…)."""
    order = _get(db, order_id, for_update=True)
    if order.status not in ("envoyee", "confirmee", "partielle"):
        raise _status_error(order, "clôturer")
    order.status = "cloturee"
    order.closed_at = now()
    order.cancel_reason = reason
    db.commit()
    return order_read(db, order)


def cancel(db: Session, order_id: int, reason: str) -> OrderRead:
    order = _get(db, order_id, for_update=True)
    if order.status not in ("a_valider", "validee", "envoyee", "confirmee"):
        raise _status_error(order, "annuler (une commande en partie reçue se clôture)")
    order.status = "annulee"
    order.cancel_reason = reason
    db.commit()
    return order_read(db, order)


# --- Réglages -------------------------------------------------------------------------


def get_settings(db: Session) -> PurchaseSettings:
    return _settings(db) or PurchaseSettings(approval_threshold=None, order_footer=None)


def save_settings(db: Session, data: SettingsIn) -> PurchaseSettings:
    settings = _settings(db)
    if settings is None:
        settings = PurchaseSettings()
        db.add(settings)
    settings.approval_threshold = data.approval_threshold
    settings.order_footer = data.order_footer
    db.commit()
    return settings
