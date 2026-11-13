"""PDF des factures et avoirs (Factur-X une fois émis) et lettre de relance."""

import io
import logging
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.modules.billing import invoices as inv
from app.modules.billing.facturx import build_xml
from app.modules.billing.models import Invoice
from app.modules.org import public as org
from app.modules.partners import public as partners
from app.shared.pdf import (
    HEAD,
    INK,
    LINE,
    embedded_fonts,
    esc,
    fdate,
    fr,
    multiline,
    page_footer,
    price,
    qty,
    styles,
)

log = logging.getLogger(__name__)

DEFAULT_PENALTY = "taux d'intérêt appliqué par la BCE à son opération de refinancement la plus récente, majoré de 10 points"  # noqa: E501
DEFAULT_DISCOUNT = "Pas d'escompte pour paiement anticipé"


def _company_block(company, s) -> Paragraph:
    lines = [f"<b>{esc(company.name)}</b>"]
    legal = " au capital de ".join(
        x
        for x in (
            company.legal_form,
            f"{fr(company.share_capital)} €" if company.share_capital else None,
        )
        if x
    )
    if legal:
        lines.append(esc(legal))
    lines += [esc(x) for x in (company.address_line1, company.address_line2) if x]
    lines.append(esc(f"{company.postal_code or ''} {company.city or ''}".strip()))
    ids = []
    if company.siren:
        ids.append(f"SIREN {company.siren}")
    if company.rcs:
        ids.append(esc(company.rcs))
    if company.vat_number:
        ids.append(f"TVA {esc(company.vat_number)}")
    if ids:
        lines.append(f'<font color="#64748b">{" · ".join(ids)}</font>')
    contact = " · ".join(x for x in (company.phone, company.email) if x)
    if contact:
        lines.append(f'<font color="#64748b">{esc(contact)}</font>')
    return Paragraph("<br/>".join(lines), s["base"])


def _grid(rows: list, widths: list, font: str = "Helvetica") -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HEAD), ("LINEBELOW", (0, 0), (-1, 0), 0.6, LINE),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("FONTNAME", (0, 0), (-1, -1), font),
        ])
    )  # fmt: skip
    return table


def render_invoice(db: Session, invoice: Invoice) -> bytes:
    company = org.get_company(db, invoice.company_id)
    font, bold = embedded_fonts()
    s = styles(font, bold)
    data = inv.read(db, invoice)
    draft = invoice.status == "brouillon"
    title = "FACTURE" if invoice.kind == "facture" else "AVOIR"
    label = f"{title.capitalize()} {invoice.number or '(brouillon)'}"
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm,
        bottomMargin=16 * mm, title=label, author=company.name, subject=label, creator="ERP",
        initialFontName=font,
    )  # fmt: skip

    refs = [Paragraph(title + (" — BROUILLON" if draft else ""), s["title"])]
    refs.append(Paragraph(f"<b>N° {esc(invoice.number or '—')}</b>", s["right"]))
    refs.append(
        Paragraph(f"Date : {fdate(invoice.issue_date) if invoice.issue_date else '—'}", s["right"])
    )
    if invoice.delivery_date:
        refs.append(Paragraph(f"Date de livraison : {fdate(invoice.delivery_date)}", s["right"]))
    if invoice.kind == "facture" and invoice.due_date:
        refs.append(Paragraph(f"Échéance : <b>{fdate(invoice.due_date)}</b>", s["right"]))
    if data.original:
        refs.append(
            Paragraph(f"Avoir sur facture n° <b>{esc(data.original.number)}</b>", s["right"])
        )
    if invoice.customer_reference:
        refs.append(Paragraph(f"Votre référence : {esc(invoice.customer_reference)}", s["right"]))
    header = Table([[_company_block(company, s), refs]], colWidths=[100 * mm, 82 * mm])
    header.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTNAME", (0, 0), (-1, -1), font)])
    )  # noqa: E501
    story = [header, Spacer(1, 7 * mm)]

    customer = [f"<b>{esc(data.customer_name)}</b>"]
    customer += [esc(x) for x in (data.customer_address or "").split("\n") if x]
    extra = [f"Client {esc(data.customer_code)}"]
    if data.customer_siren:
        extra.append(f"SIREN {data.customer_siren}")
    if data.customer_vat:
        extra.append(f"TVA {esc(data.customer_vat)}")
    customer.append(f'<font color="#64748b">{" · ".join(extra)}</font>')
    deliveries = ", ".join(sorted({x.delivery_number for x in invoice.lines if x.delivery_number}))
    info = [
        "Opération : livraison de biens"
        + (
            " et prestations de services"
            if any(x.article_id is None for x in invoice.lines)
            else ""
        )
    ]
    if deliveries:
        info.append(f"Bons de livraison : {esc(deliveries)}")
    if invoice.kind == "avoir" and invoice.note:
        info.append(f"Motif : {esc(invoice.note)}")
    boxes = Table(
        [
            [Paragraph("FACTURÉ À", s["small"]), Paragraph("INFORMATIONS", s["small"])],
            [
                Paragraph("<br/>".join(customer), s["base"]),
                Paragraph("<br/>".join(info), s["base"]),
            ],
        ],
        colWidths=[91 * mm, 91 * mm],
    )
    boxes.setStyle(
        TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font), ("BOX", (0, 0), (0, -1), 0.6, LINE), ("BOX", (1, 0), (1, -1), 0.6, LINE),  # noqa: E501
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
        ])
    )  # fmt: skip
    story += [boxes, Spacer(1, 5 * mm)]

    has_discount = any(x.discount_pct for x in invoice.lines)
    has_eco = any(x.eco_fee for x in invoice.lines)
    head = ["Réf.", "Désignation", "Qté", "P.U. HT"] + (["Rem."] if has_discount else [])
    head += (["Éco"] if has_eco else []) + ["TVA", "Total HT"]
    rows = [[Paragraph(f"<b>{h}</b>", s["small"]) for h in head]]
    for x in invoice.lines:
        designation = esc(x.designation)
        if x.delivery_number and "," in deliveries:
            designation += f'<br/><font size="7" color="#64748b">{esc(x.delivery_number)}</font>'
        row = [
            Paragraph(esc(x.article_code or ""), s["tiny"]),
            Paragraph(designation, s["base"]),
            Paragraph(qty(x.quantity), s["right"]),
            Paragraph(price(x.unit_price), s["right"]),
        ]
        if has_discount:
            row.append(Paragraph(f"{fr(x.discount_pct)} %" if x.discount_pct else "", s["right"]))
        if has_eco:
            row.append(Paragraph(fr(inv.eco_total(x)) if x.eco_fee else "", s["right"]))
        row += [
            Paragraph(f"{qty(x.vat_rate)} %", s["right"]),
            Paragraph(fr(x.line_total + inv.eco_total(x)), s["right"]),
        ]
        rows.append(row)
    fixed = 20 + 14 + 18 + (13 if has_discount else 0) + (14 if has_eco else 0) + 14 + 21
    widths = [20 * mm, (182 - fixed) * mm, 14 * mm, 18 * mm]
    widths += [13 * mm] if has_discount else []
    widths += [14 * mm] if has_eco else []
    widths += [14 * mm, 21 * mm]
    story += [_grid(rows, widths, font), Spacer(1, 4 * mm)]

    totals = [
        [Paragraph("Total HT", s["base"]), Paragraph(f"{fr(invoice.total_ht)} €", s["right"])]
    ]
    if invoice.total_eco:
        totals.append(
            [
                Paragraph("dont éco-contribution", s["small"]),
                Paragraph(f"{fr(invoice.total_eco)} €", s["right"]),
            ]
        )
    for v in data.vat:
        totals.append(
            [
                Paragraph(f"TVA {qty(v.rate)} % sur {fr(v.base)}", s["base"]),
                Paragraph(f"{fr(v.vat)} €", s["right"]),
            ]
        )
    totals.append(
        [
            Paragraph("Total TTC", s["bold"]),
            Paragraph(f"<b>{fr(invoice.total_ttc)} €</b>", s["right"]),
        ]
    )
    # Pas de « déjà réglé » : une facture émise doit se réimprimer à l'identique, quels que
    # soient les règlements reçus depuis (ils sont suivis dans l'ERP, pas sur la facture).
    table = Table(totals, colWidths=[56 * mm, 34 * mm], hAlign="RIGHT")
    table.setStyle(
        TableStyle(
            [
                (
                    "LINEABOVE",
                    (0, 1 + len(data.vat) + (1 if invoice.total_eco else 0)),
                    (-1, 1 + len(data.vat) + (1 if invoice.total_eco else 0)),
                    1,
                    INK,
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("FONTNAME", (0, 0), (-1, -1), font),
            ]
        )
    )
    story += [table, Spacer(1, 6 * mm)]

    # Mentions légales (art. L441-9 et D441-5 du Code de commerce).
    mentions = []
    if invoice.kind == "facture":
        terms = f"<b>Règlement :</b> {esc(data.payment_terms or 'à réception')}"
        if invoice.due_date:
            terms += f", échéance le {fdate(invoice.due_date)}"
        mentions.append(terms)
        if company.iban:
            mentions.append(
                f"<b>IBAN :</b> {esc(company.iban)}"
                + (f" — <b>BIC :</b> {esc(company.bic)}" if company.bic else "")
            )
        mentions.append(esc(company.early_payment_discount or DEFAULT_DISCOUNT) + ".")
        mentions.append(
            f"En cas de retard de paiement, pénalités au {esc(company.late_penalty or DEFAULT_PENALTY)}."  # noqa: E501
        )
        if data.customer_kind != "particulier":
            mentions.append(
                "Indemnité forfaitaire pour frais de recouvrement en cas de retard : 40 €."
            )
    elif invoice.note:
        pass  # le motif de l'avoir est déjà dans l'encadré
    if invoice.note and invoice.kind == "facture":
        mentions.append(multiline(invoice.note))
    for m in mentions:
        story += [Paragraph(m, s["small"]), Spacer(1, 1.2 * mm)]
    if company.invoice_footer:
        story += [Spacer(1, 3 * mm), Paragraph(multiline(company.invoice_footer), s["tiny"])]

    footer = page_footer(f"{company.name} — {label}", font)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    pdf = buffer.getvalue()
    if draft:
        return pdf
    return _facturx(db, invoice, company, pdf)


def invoice_xml(db: Session, invoice: Invoice) -> bytes:
    company = org.get_company(db, invoice.company_id)
    terms = partners.customer_terms(db, invoice.customer_id)
    original = inv.get(db, invoice.original_id).number if invoice.original_id else None
    return build_xml(invoice, company, terms.payment_method, original)


def _facturx(db: Session, invoice: Invoice, company, pdf: bytes) -> bytes:
    """Attache le XML CII au PDF (PDF/A-3 « Factur-X », profil EN 16931)."""
    from facturx import generate_from_binary

    xml = invoice_xml(db, invoice)
    metadata = {
        "author": company.name,
        "keywords": "Factur-X, facture",
        "title": f"{company.name} : {'Facture' if invoice.kind == 'facture' else 'Avoir'} {invoice.number}",  # noqa: E501
        "subject": f"{'Facture' if invoice.kind == 'facture' else 'Avoir'} {invoice.number} du {fdate(invoice.issue_date)}",  # noqa: E501
    }
    return generate_from_binary(
        pdf,
        xml,
        flavor="factur-x",
        level="en16931",
        check_xsd=True,
        pdf_metadata=metadata,
        lang="fr-FR",
    )


def render_reminder(db: Session, customer_id: int, invoices: list[Invoice]) -> bytes:
    """Lettre de relance : les factures échues, le total dû, les pénalités applicables."""
    company = org.get_company(db, invoices[0].company_id)
    terms = partners.customer_terms(db, customer_id)
    font, bold = embedded_fonts()
    s = styles(font, bold)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title="Relance",
        initialFontName=font,
        author=company.name,
    )
    level = max(x.reminder_count for x in invoices)
    title = {1: "Rappel d'échéance", 2: "Deuxième relance"}.get(level, "Mise en demeure de payer")
    address = [f"<b>{esc(terms.name)}</b>"] + [esc(x) for x in terms.billing_address]
    header = Table(
        [[_company_block(company, s), Paragraph("<br/>".join(address), s["base"])]],
        colWidths=[95 * mm, 79 * mm],
    )
    header.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTNAME", (0, 0), (-1, -1), font)])
    )  # noqa: E501
    story = [
        header,
        Spacer(1, 10 * mm),
        Paragraph(f"{esc(company.city or '')}, le {fdate(date.today())}", s["right"]),
        Spacer(1, 6 * mm),
    ]
    story += [Paragraph(f"<b>Objet : {title}</b>", s["base"]), Spacer(1, 4 * mm)]
    total = sum((inv.balance(x) for x in invoices), invoices[0].total_ttc * 0)
    text = (
        "Madame, Monsieur,<br/><br/>Sauf erreur ou omission de notre part, les factures ci-dessous "
        "restent impayées à ce jour. Nous vous remercions de bien vouloir procéder à leur règlement "  # noqa: E501
        "dans les meilleurs délais. Si votre paiement a été émis entre-temps, merci de ne pas tenir "  # noqa: E501
        "compte de ce courrier."
    )
    story += [Paragraph(text, s["base"]), Spacer(1, 5 * mm)]
    rows = [
        [
            Paragraph(f"<b>{h}</b>", s["small"])
            for h in ("Facture", "Date", "Échéance", "Retard", "Montant TTC", "Reste dû")
        ]
    ]
    for x in invoices:
        rows.append([
            Paragraph(esc(x.number), s["base"]), Paragraph(fdate(x.issue_date), s["base"]),
            Paragraph(fdate(x.due_date), s["base"]), Paragraph(f"{inv.days_late(x)} j", s["right"]),
            Paragraph(fr(x.total_ttc), s["right"]), Paragraph(fr(inv.balance(x)), s["right"]),
        ])  # fmt: skip
    rows.append(
        [
            Paragraph("<b>Total dû</b>", s["base"]),
            "",
            "",
            "",
            "",
            Paragraph(f"<b>{fr(total)} €</b>", s["right"]),
        ]
    )
    story += [
        _grid(rows, [34 * mm, 24 * mm, 24 * mm, 20 * mm, 36 * mm, 36 * mm], font),
        Spacer(1, 6 * mm),
    ]
    penalty = f"Conformément à nos conditions, des pénalités de retard au {esc(company.late_penalty or DEFAULT_PENALTY)} sont exigibles"  # noqa: E501
    if terms.kind != "particulier":
        penalty += ", ainsi que l'indemnité forfaitaire de 40 € pour frais de recouvrement"
    story += [Paragraph(penalty + ".", s["base"]), Spacer(1, 4 * mm)]
    if company.iban:
        story += [
            Paragraph(
                f"Règlement par virement : IBAN {esc(company.iban)}"
                + (f" — BIC {esc(company.bic)}" if company.bic else ""),
                s["base"],
            ),
            Spacer(1, 6 * mm),
        ]
    story += [
        Paragraph(
            "Nous vous prions d'agréer, Madame, Monsieur, nos salutations distinguées.", s["base"]
        ),
        Spacer(1, 10 * mm),
        Paragraph(f"Le service comptabilité — {esc(company.name)}", s["base"]),
    ]
    footer = page_footer(f"{company.name} — {title}", font)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
