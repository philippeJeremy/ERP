"""Outils communs aux documents PDF (reportlab) : couleurs, styles, formats français."""

from datetime import date
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm

INK = colors.HexColor("#1e293b")
MUTED = colors.HexColor("#64748b")
LINE = colors.HexColor("#cbd5e1")
HEAD = colors.HexColor("#f1f5f9")


def fr(value: Decimal, decimals: int = 2) -> str:
    """1234.5 → « 1 234,50 »."""
    return f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")


def price(value: Decimal) -> str:
    """Prix unitaire : 2 décimales, ou 4 si nécessaire."""
    return fr(value, 4 if value != value.quantize(Decimal("0.01")) else 2)


def qty(value: Decimal) -> str:
    return fr(value, 3).rstrip("0").rstrip(",")


def fdate(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else "—"


def esc(text: str | None) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def multiline(text: str | None) -> str:
    return esc(text).replace("\n", "<br/>")


def styles() -> dict[str, ParagraphStyle]:
    sheet = getSampleStyleSheet()
    base = ParagraphStyle("base", parent=sheet["Normal"], fontSize=9, leading=12, textColor=INK)
    return {
        "base": base,
        "small": ParagraphStyle("small", parent=base, fontSize=8, leading=10, textColor=MUTED),
        "title": ParagraphStyle(
            "title", parent=base, fontSize=18, leading=22, fontName="Helvetica-Bold"
        ),
        "right": ParagraphStyle("right", parent=base, alignment=TA_RIGHT),
        "bold": ParagraphStyle("bold", parent=base, fontName="Helvetica-Bold"),
    }


def company_lines(company) -> list[str]:
    """Bloc société (en-tête) : nom, adresse, SIREN, TVA."""
    lines = [f"<b>{esc(company.name)}</b>"]
    lines += [esc(x) for x in (company.address_line1, company.address_line2) if x]
    if company.postal_code or company.city:
        lines.append(esc(f"{company.postal_code or ''} {company.city or ''}".strip()))
    ids = []
    if company.siren:
        ids.append(f"SIREN {company.siren}")
    if company.vat_number:
        ids.append(f"TVA {company.vat_number}")
    if ids:
        lines.append(f'<font color="#64748b">{" · ".join(ids)}</font>')
    return lines


def page_footer(label: str):
    """Pied de page « label — Page n » pour SimpleDocTemplate.build()."""

    def draw(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(16 * mm, 9 * mm, label)
        canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"Page {document.page}")
        canvas.restoreState()

    return draw
