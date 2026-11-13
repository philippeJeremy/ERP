"""Bon de commande au format PDF (bibliothèque reportlab, sans dépendance système).

Le document est produit à la demande, jamais stocké : il est toujours le reflet exact
de la commande en base.
"""

import io
from datetime import date
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.modules.org import public as org
from app.modules.partners import public as partners
from app.modules.purchasing import repository as repo
from app.modules.purchasing.models import PurchaseOrder

INK = colors.HexColor("#1e293b")
MUTED = colors.HexColor("#64748b")
LINE = colors.HexColor("#cbd5e1")
HEAD = colors.HexColor("#f1f5f9")


def _fr(value: Decimal, decimals: int = 2) -> str:
    """1234.5 → « 1 234,50 » (format français, espace insécable fine)."""
    text = f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")
    return text


def _qty(value: Decimal) -> str:
    return _fr(value, 3).rstrip("0").rstrip(",")


def _date(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else "—"


def _esc(text: str | None) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(db: Session, order: PurchaseOrder) -> bytes:
    company = org.get_company(db, order.company_id)
    supplier = partners.supplier_terms(db, order.partner_id)
    site = org.get_site(db, order.site_id)
    settings = repo.get_settings(db)

    styles = getSampleStyleSheet()
    base = ParagraphStyle("base", parent=styles["Normal"], fontSize=9, leading=12, textColor=INK)
    small = ParagraphStyle("small", parent=base, fontSize=8, leading=10, textColor=MUTED)
    title = ParagraphStyle("title", parent=base, fontSize=18, leading=22, fontName="Helvetica-Bold")
    right = ParagraphStyle("right", parent=base, alignment=TA_RIGHT)
    bold = ParagraphStyle("bold", parent=base, fontName="Helvetica-Bold")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=14 * mm, bottomMargin=16 * mm,
        title=f"Bon de commande {order.number}", author=company.name,
    )  # fmt: skip
    story = []

    # En-tête : la société à gauche, le titre et les références à droite.
    company_lines = [f"<b>{_esc(company.name)}</b>"]
    company_lines += [_esc(x) for x in (company.address_line1, company.address_line2) if x]
    if company.postal_code or company.city:
        company_lines.append(_esc(f"{company.postal_code or ''} {company.city or ''}".strip()))
    ids = []
    if company.siren:
        ids.append(f"SIREN {company.siren}")
    if company.vat_number:
        ids.append(f"TVA {company.vat_number}")
    if ids:
        company_lines.append(f'<font color="#64748b">{" · ".join(ids)}</font>')
    refs = [
        Paragraph("BON DE COMMANDE", title),
        Paragraph(f"<b>N° {_esc(order.number)}</b>", right),
        Paragraph(f"Date : {_date(order.order_date)}", right),
    ]
    if order.expected_date:
        refs.append(Paragraph(f"Livraison souhaitée : <b>{_date(order.expected_date)}</b>", right))
    header = Table(
        [[Paragraph("<br/>".join(company_lines), base), refs]], colWidths=[95 * mm, 83 * mm]
    )
    header.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT")])
    )
    story += [header, Spacer(1, 8 * mm)]

    # Fournisseur et adresse de livraison côte à côte.
    supplier_lines = [f"<b>{_esc(supplier.name)}</b>"] + [_esc(x) for x in supplier.order_address]
    supplier_lines.append(
        f'<font color="#64748b">Code fournisseur chez nous : {supplier.code}</font>'
    )
    site_lines = [f"<b>{_esc(company.name)} — {_esc(site.name)}</b>"]
    site_lines += [_esc(x) for x in (site.address_line1, site.address_line2) if x]
    site_lines.append(_esc(f"{site.postal_code} {site.city}"))
    if site.phone:
        site_lines.append(f"Tél. {_esc(site.phone)}")
    if site.gln:
        site_lines.append(f'<font color="#64748b">GLN {site.gln}</font>')
    if site.delivery_notes:
        site_lines.append(f"<i>{_esc(site.delivery_notes)}</i>")
    boxes = Table(
        [
            [Paragraph("FOURNISSEUR", small), Paragraph("ADRESSE DE LIVRAISON", small)],
            [
                Paragraph("<br/>".join(supplier_lines), base),
                Paragraph("<br/>".join(site_lines), base),
            ],
        ],
        colWidths=[89 * mm, 89 * mm],
    )
    boxes.setStyle(
        TableStyle([
            ("BOX", (0, 0), (0, -1), 0.6, LINE), ("BOX", (1, 0), (1, -1), 0.6, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ])
    )  # fmt: skip
    story += [boxes, Spacer(1, 6 * mm)]

    # Lignes.
    has_discount = any(line.discount_pct for line in order.lines)
    head = (
        ["Réf. fournisseur", "Désignation", "Qté", "P.U. HT"]
        + (["Remise"] if has_discount else [])
        + ["Total HT"]
    )
    rows = [[Paragraph(f"<b>{h}</b>", small) for h in head]]
    for line in order.lines:
        row = [
            Paragraph(_esc(line.supplier_ref) or "—", base),
            Paragraph(_esc(line.designation), base),
            Paragraph(_qty(line.quantity), right),
            Paragraph(
                _fr(
                    line.unit_price,
                    4 if line.unit_price != line.unit_price.quantize(Decimal("0.01")) else 2,
                ),
                right,
            ),
        ]
        if has_discount:
            row.append(Paragraph(f"{_fr(line.discount_pct)} %" if line.discount_pct else "", right))
        row.append(Paragraph(_fr(line.line_total), right))
        rows.append(row)
    widths = (
        [30 * mm, (78 if has_discount else 94) * mm, 16 * mm, 20 * mm]
        + ([16 * mm] if has_discount else [])
        + [22 * mm]
    )
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HEAD), ("LINEBELOW", (0, 0), (-1, 0), 0.6, LINE),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )  # fmt: skip
    story += [table, Spacer(1, 4 * mm)]

    total = Table(
        [
            [
                Paragraph("Total HT", bold),
                Paragraph(f"<b>{_fr(order.total_ht)} {order.currency}</b>", right),
            ]
        ],
        colWidths=[40 * mm, 38 * mm],
        hAlign="RIGHT",
    )
    total.setStyle(
        TableStyle([("LINEABOVE", (0, 0), (-1, 0), 1, INK), ("TOPPADDING", (0, 0), (-1, -1), 6)])
    )
    story += [total, Spacer(1, 6 * mm)]

    # Conditions et mentions.
    notes = []
    if supplier.payment_terms:
        notes.append(f"<b>Règlement :</b> {_esc(supplier.payment_terms)}")
    if order.supplier_note:
        notes.append(_esc(order.supplier_note).replace("\n", "<br/>"))
    notes.append(
        f"Merci de rappeler le n° <b>{_esc(order.number)}</b> sur votre accusé de commande, "
        "votre bon de livraison et votre facture."
    )
    for note in notes:
        story += [Paragraph(note, base), Spacer(1, 2 * mm)]
    if settings and settings.order_footer:
        story += [
            Spacer(1, 4 * mm),
            Paragraph(_esc(settings.order_footer).replace("\n", "<br/>"), small),
        ]

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(16 * mm, 9 * mm, f"{company.name} — Bon de commande {order.number}")
        canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
