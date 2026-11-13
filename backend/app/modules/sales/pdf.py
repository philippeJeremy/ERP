"""Devis et bon de livraison au format PDF (produits à la demande, jamais stockés)."""

import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.modules.inventory import public as inventory
from app.modules.org import public as org
from app.modules.partners import public as partners
from app.modules.sales import repository as repo
from app.modules.sales.models import Delivery, Quote, SalesOrder
from app.modules.sales.service import _eco_total, _vat_rows
from app.shared.pdf import (
    HEAD,
    INK,
    LINE,
    company_lines,
    esc,
    fdate,
    fr,
    multiline,
    page_footer,
    price,
    qty,
    styles,
)


def _doc(buffer: io.BytesIO, title: str, author: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=14 * mm, bottomMargin=16 * mm, title=title, author=author,
    )  # fmt: skip


def _header(company, s, title: str, refs: list[str]) -> Table:
    right = [Paragraph(title, s["title"])] + [Paragraph(r, s["right"]) for r in refs]
    table = Table(
        [[Paragraph("<br/>".join(company_lines(company)), s["base"]), right]],
        colWidths=[95 * mm, 83 * mm],
    )
    table.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT")])
    )
    return table


def _boxes(s, left: tuple[str, list[str]], right: tuple[str, list[str]]) -> Table:
    table = Table(
        [
            [Paragraph(left[0], s["small"]), Paragraph(right[0], s["small"])],
            [
                Paragraph("<br/>".join(left[1]), s["base"]),
                Paragraph("<br/>".join(right[1]), s["base"]),
            ],
        ],
        colWidths=[89 * mm, 89 * mm],
    )
    table.setStyle(
        TableStyle([
            ("BOX", (0, 0), (0, -1), 0.6, LINE), ("BOX", (1, 0), (1, -1), 0.6, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ])
    )  # fmt: skip
    return table


def _grid(rows: list, widths: list) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HEAD), ("LINEBELOW", (0, 0), (-1, 0), 0.6, LINE),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )  # fmt: skip
    return table


def _customer_lines(terms: partners.CustomerTerms, address: list[str]) -> list[str]:
    lines = [f"<b>{esc(terms.name)}</b>"] + [esc(x) for x in address]
    extra = [f"Client {terms.code}"]
    if terms.vat_number:
        extra.append(f"TVA {terms.vat_number}")
    if terms.vehicle_registration:
        extra.append(f"Véhicule {terms.vehicle_registration}")
    lines.append(f'<font color="#64748b">{" · ".join(extra)}</font>')
    return lines


def render_quote(db: Session, quote: Quote) -> bytes:
    company = org.get_company(db, quote.company_id)
    terms = partners.customer_terms(db, quote.customer_id)
    settings = repo.get_settings(db)
    s = styles()
    buffer = io.BytesIO()
    doc = _doc(buffer, f"Devis {quote.number}", company.name)
    refs = [
        f"<b>N° {esc(quote.number)}</b>",
        f"Date : {fdate(quote.quote_date)}",
        f"Valable jusqu'au <b>{fdate(quote.valid_until)}</b>",
    ]
    if quote.customer_reference:
        refs.append(f"Votre référence : {esc(quote.customer_reference)}")
    story = [_header(company, s, "DEVIS", refs), Spacer(1, 8 * mm)]
    site = org.get_site(db, quote.site_id)
    site_lines = [f"<b>{esc(site.name)}</b>"]
    site_lines += [esc(x) for x in (site.address_line1, site.address_line2) if x]
    site_lines.append(esc(f"{site.postal_code} {site.city}"))
    if site.phone:
        site_lines.append(f"Tél. {esc(site.phone)}")
    story += [
        _boxes(
            s,
            ("CLIENT", _customer_lines(terms, terms.billing_address)),
            ("VOTRE INTERLOCUTEUR", site_lines),
        ),
        Spacer(1, 6 * mm),
    ]
    story += _lines_table(s, quote)
    story += _totals(s, quote)
    notes = []
    if terms.payment_terms:
        notes.append(f"<b>Règlement :</b> {esc(terms.payment_terms)}")
    if quote.customer_note:
        notes.append(multiline(quote.customer_note))
    notes.append("Bon pour accord (date, signature et cachet) :")
    for note in notes:
        story += [Paragraph(note, s["base"]), Spacer(1, 2 * mm)]
    if settings and settings.quote_footer:
        story += [Spacer(1, 10 * mm), Paragraph(multiline(settings.quote_footer), s["small"])]
    footer = page_footer(f"{company.name} — Devis {quote.number}")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _lines_table(s, doc_: Quote | SalesOrder) -> list:
    has_discount = any(x.discount_pct for x in doc_.lines)
    has_eco = any(x.eco_fee for x in doc_.lines)
    head = ["Désignation", "Qté", "P.U. HT"]
    head += ["Remise"] if has_discount else []
    head += ["Éco"] if has_eco else []
    head += ["Total HT"]
    rows = [[Paragraph(f"<b>{h}</b>", s["small"]) for h in head]]
    for line in doc_.lines:
        row = [
            Paragraph(esc(line.designation), s["base"]),
            Paragraph(qty(line.quantity), s["right"]),
            Paragraph(price(line.unit_price), s["right"]),
        ]
        if has_discount:
            row.append(
                Paragraph(f"{fr(line.discount_pct)} %" if line.discount_pct else "", s["right"])
            )
        if has_eco:
            row.append(Paragraph(fr(_eco_total(line)) if line.eco_fee else "", s["right"]))
        row.append(Paragraph(fr(line.line_total + _eco_total(line)), s["right"]))
        rows.append(row)
    fixed = 16 + 20 + (16 if has_discount else 0) + (18 if has_eco else 0) + 22
    widths = [(178 - fixed) * mm, 16 * mm, 20 * mm]
    widths += [16 * mm] if has_discount else []
    widths += [18 * mm] if has_eco else []
    widths += [22 * mm]
    return [_grid(rows, widths), Spacer(1, 4 * mm)]


def _totals(s, doc_: Quote | SalesOrder) -> list:
    rows = [[Paragraph("Total HT", s["base"]), Paragraph(f"{fr(doc_.total_ht)} €", s["right"])]]
    if doc_.total_eco:
        rows.append(
            [
                Paragraph("dont éco-contribution", s["small"]),
                Paragraph(f"{fr(doc_.total_eco)} €", s["right"]),
            ]
        )
    for vat in _vat_rows(doc_):
        rows.append(
            [
                Paragraph(f"TVA {fr(vat.rate)} % sur {fr(vat.base)}", s["base"]),
                Paragraph(f"{fr(vat.vat)} €", s["right"]),
            ]
        )
    rows.append(
        [Paragraph("Total TTC", s["bold"]), Paragraph(f"<b>{fr(doc_.total_ttc)} €</b>", s["right"])]
    )
    table = Table(rows, colWidths=[52 * mm, 34 * mm], hAlign="RIGHT")
    table.setStyle(
        TableStyle([
            ("LINEABOVE", (0, -1), (-1, -1), 1, INK), ("TOPPADDING", (0, 0), (-1, -1), 3),
        ])
    )  # fmt: skip
    return [table, Spacer(1, 6 * mm)]


def render_delivery(db: Session, order: SalesOrder, delivery: Delivery) -> bytes:
    """Bon de livraison : quantités livrées et DOT, SANS prix (il voyage avec la marchandise)."""
    company = org.get_company(db, order.company_id)
    terms = partners.customer_terms(db, order.customer_id)
    settings = repo.get_settings(db)
    site = org.get_site(db, delivery.site_id)
    s = styles()
    buffer = io.BytesIO()
    doc = _doc(buffer, f"Bon de livraison {delivery.number}", company.name)
    refs = [
        f"<b>N° {esc(delivery.number)}</b>",
        f"Date : {fdate(delivery.delivered_on)}",
        f"Commande {esc(order.number)} du {fdate(order.order_date)}",
    ]
    if order.customer_reference:
        refs.append(f"Votre référence : {esc(order.customer_reference)}")
    story = [_header(company, s, "BON DE LIVRAISON", refs), Spacer(1, 8 * mm)]
    address = (order.delivery_address or "").split("\n")
    delivery_lines = [f"<b>{esc(address[0])}</b>"] + [esc(x) for x in address[1:]]
    if terms.phone:
        delivery_lines.append(f"Tél. {esc(terms.phone)}")
    site_lines = [
        f"<b>{esc(company.name)} — {esc(site.name)}</b>",
        esc(f"{site.postal_code} {site.city}"),
    ]
    if delivery.carrier:
        site_lines.append(f"Transport : {esc(delivery.carrier)}")
    story += [
        _boxes(s, ("LIVRÉ À", delivery_lines), ("EXPÉDIÉ PAR", site_lines)),
        Spacer(1, 6 * mm),
    ]
    lines = {x.id: x for x in order.lines}
    locations = inventory.location_codes(
        db, {x.location_id for x in delivery.lines if x.location_id}
    )
    rows = [[Paragraph(f"<b>{h}</b>", s["small"]) for h in ("Désignation", "DOT", "Empl.", "Qté")]]
    for x in delivery.lines:
        rows.append(
            [
                Paragraph(esc(lines[x.order_line_id].designation), s["base"]),
                Paragraph(x.dot or "", s["base"]),
                Paragraph(esc(locations.get(x.location_id, "")), s["small"]),
                Paragraph(qty(x.quantity), s["right"]),
            ]
        )
    story += [_grid(rows, [118 * mm, 20 * mm, 22 * mm, 18 * mm]), Spacer(1, 6 * mm)]
    if delivery.note:
        story += [Paragraph(multiline(delivery.note), s["base"]), Spacer(1, 4 * mm)]
    sign = Table(
        [
            [
                Paragraph("Préparé par :", s["base"]),
                Paragraph("Reçu le, signature du client :", s["base"]),
            ]
        ],
        colWidths=[89 * mm, 89 * mm],
        rowHeights=[24 * mm],
    )
    sign.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (0, 0), 0.6, LINE),
                ("BOX", (1, 0), (1, 0), 0.6, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(sign)
    if settings and settings.delivery_footer:
        story += [Spacer(1, 6 * mm), Paragraph(multiline(settings.delivery_footer), s["small"])]
    footer = page_footer(f"{company.name} — Bon de livraison {delivery.number}")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
