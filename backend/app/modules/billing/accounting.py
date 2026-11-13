"""Export comptable : écritures de ventes, d'achats et de banque, en CSV ou au format FEC.

Chaque pièce donne une écriture équilibrée (débit = crédit) :

    Facture client  411 Client (débit TTC) / 707 Ventes, 706 Prestations, 7085 Éco
                    (crédit HT) / 44571 TVA collectée (crédit)   — avoir : l'inverse
    Facture fourn.  607 Achats (débit HT) / 44566 TVA déductible (débit) / 401 (crédit TTC)
    Règlement       512 Banque (ou 530 Caisse) / 411 Client ; paiement fournisseur : 401 / 512

Le FEC (Fichier des Écritures Comptables, art. A47 A-1 du LPF) est le format exigé par
l'administration fiscale : 18 colonnes séparées par des tabulations.
"""

import csv
import io
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.billing.common import ZERO, get_settings, money
from app.modules.billing.invoices import eco_total
from app.modules.billing.models import Invoice, Payment, SupplierInvoice, SupplierPayment
from app.modules.billing.schemas import EntriesPage, Entry
from app.modules.org import public as org
from app.modules.partners import public as partners

LABELS = {
    "customer_account": "Clients",
    "supplier_account": "Fournisseurs",
    "sales_goods_account": "Ventes de marchandises",
    "sales_services_account": "Prestations de services",
    "eco_fee_account": "Éco-contributions refacturées",
    "vat_collected_account": "TVA collectée",
    "purchases_account": "Achats de marchandises",
    "vat_deductible_account": "TVA déductible sur biens et services",
    "bank_account": "Banque",
    "cash_account": "Caisse",
}


def _entry(journal, day, piece, account, label, debit=ZERO, credit=ZERO, aux=None, aux_label=None):
    return Entry(
        journal=journal, date=day, piece=piece, account=account, aux_account=aux,
        aux_label=aux_label, label=label[:100], debit=money(debit), credit=money(credit),
    )  # fmt: skip


def entries(db: Session, start: date, end: date) -> EntriesPage:
    s = get_settings(db)
    result: list[Entry] = []

    # --- Ventes : factures et avoirs émis.
    invoices = db.scalars(
        select(Invoice)
        .where(Invoice.status == "emise", Invoice.issue_date.between(start, end))
        .order_by(Invoice.issue_date, Invoice.number)
    )
    customer_terms: dict[int, partners.CustomerTerms] = {}
    for x in invoices:
        terms = customer_terms.setdefault(x.customer_id, partners.customer_terms(db, x.customer_id))
        sign = 1 if x.kind == "facture" else -1
        label = f"{'Facture' if x.kind == 'facture' else 'Avoir'} {x.number} {x.customer_name}"
        account = terms.customer_account or s.customer_account

        def side(amount: Decimal, sign: int = sign) -> tuple[Decimal, Decimal]:
            value = amount * sign
            return (value, ZERO) if value >= 0 else (ZERO, -value)

        debit, credit = side(x.total_ttc)
        result.append(
            _entry(
                s.sales_journal,
                x.issue_date,
                x.number,
                account,
                label,
                debit,
                credit,
                x.customer_code,
                x.customer_name,
            )  # fmt: skip
        )
        revenue: dict[str, Decimal] = {}
        for line in x.lines:
            key = s.sales_goods_account if line.article_id else s.sales_services_account
            revenue[key] = revenue.get(key, ZERO) + line.line_total
            if line.eco_fee:
                revenue[s.eco_fee_account] = revenue.get(s.eco_fee_account, ZERO) + eco_total(line)
        for key, amount in revenue.items():
            debit, credit = side(-amount)
            result.append(
                _entry(s.sales_journal, x.issue_date, x.number, key, label, debit, credit)
            )
        if x.total_vat:
            debit, credit = side(-x.total_vat)
            result.append(
                _entry(
                    s.sales_journal,
                    x.issue_date,
                    x.number,
                    s.vat_collected_account,
                    label,
                    debit,
                    credit,
                )  # fmt: skip
            )

    # --- Achats : factures fournisseur validées (bon à payer).
    supplier_invoices = db.scalars(
        select(SupplierInvoice)
        .where(
            SupplierInvoice.status == "bon_a_payer",
            SupplierInvoice.invoice_date.between(start, end),
        )
        .order_by(SupplierInvoice.invoice_date, SupplierInvoice.number)
    )
    supplier_terms: dict[int, partners.SupplierTerms] = {}
    for x in supplier_invoices:
        terms = supplier_terms.setdefault(x.partner_id, partners.supplier_terms(db, x.partner_id))
        label = f"Facture {x.supplier_number} {terms.name}"
        result.append(
            _entry(
                s.purchases_journal,
                x.invoice_date,
                x.number,
                s.purchases_account,
                label,
                debit=x.total_ht,
            )  # fmt: skip
        )
        if x.total_vat:
            result.append(
                _entry(
                    s.purchases_journal,
                    x.invoice_date,
                    x.number,
                    s.vat_deductible_account,
                    label,
                    debit=x.total_vat,
                )  # fmt: skip
            )
        result.append(
            _entry(
                s.purchases_journal,
                x.invoice_date,
                x.number,
                terms.supplier_account or s.supplier_account,
                label,
                credit=x.total_ht + x.total_vat,
                aux=terms.code,
                aux_label=terms.name,
            )  # fmt: skip
        )

    # --- Banque : règlements clients, paiements fournisseurs.
    payments = db.scalars(
        select(Payment)
        .where(Payment.paid_on.between(start, end))
        .order_by(Payment.paid_on, Payment.number)
    )
    for p in payments:
        terms = customer_terms.setdefault(p.customer_id, partners.customer_terms(db, p.customer_id))
        cash = s.cash_account if p.method == "especes" else s.bank_account
        label = f"Règlement {p.number} {terms.name}"
        result.append(_entry(s.bank_journal, p.paid_on, p.number, cash, label, debit=p.amount))
        result.append(
            _entry(
                s.bank_journal,
                p.paid_on,
                p.number,
                terms.customer_account or s.customer_account,
                label,
                credit=p.amount,
                aux=terms.code,
                aux_label=terms.name,
            )  # fmt: skip
        )
    rows = db.execute(
        select(SupplierPayment, SupplierInvoice)
        .join(SupplierInvoice, SupplierInvoice.id == SupplierPayment.supplier_invoice_id)
        .where(SupplierPayment.paid_on.between(start, end))
        .order_by(SupplierPayment.paid_on, SupplierPayment.id)
    ).all()
    for p, x in rows:
        terms = supplier_terms.setdefault(x.partner_id, partners.supplier_terms(db, x.partner_id))
        cash = s.cash_account if p.method == "especes" else s.bank_account
        piece = f"{x.number}-P{p.id}"
        label = f"Paiement facture {x.supplier_number} {terms.name}"
        result.append(
            _entry(
                s.bank_journal,
                p.paid_on,
                piece,
                terms.supplier_account or s.supplier_account,
                label,
                debit=p.amount,
                aux=terms.code,
                aux_label=terms.name,
            )  # fmt: skip
        )
        result.append(_entry(s.bank_journal, p.paid_on, piece, cash, label, credit=p.amount))

    return EntriesPage(
        entries=result,
        total_debit=sum((e.debit for e in result), ZERO),
        total_credit=sum((e.credit for e in result), ZERO),
    )


def _fr(value: Decimal) -> str:
    return f"{value:.2f}".replace(".", ",")


def to_csv(page: EntriesPage) -> str:
    """CSV « à la française » (point-virgule, virgule décimale), lisible par Excel."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        ["Journal", "Date", "Pièce", "Compte", "Compte auxiliaire", "Libellé", "Débit", "Crédit"]
    )
    for e in page.entries:
        writer.writerow(
            [
                e.journal,
                e.date.strftime("%d/%m/%Y"),
                e.piece,
                e.account,
                e.aux_account or "",
                e.label,
                _fr(e.debit),
                _fr(e.credit),
            ]  # fmt: skip
        )
    return "﻿" + out.getvalue()  # BOM : Excel reconnaît l'UTF-8 (accents)


FEC_COLUMNS = [
    "JournalCode", "JournalLib", "EcritureNum", "EcritureDate", "CompteNum", "CompteLib",
    "CompAuxNum", "CompAuxLib", "PieceRef", "PieceDate", "EcritureLib", "Debit", "Credit",
    "EcritureLet", "DateLet", "ValidDate", "Montantdevise", "Idevise",
]  # fmt: skip


def to_fec(db: Session, page: EntriesPage) -> str:
    s = get_settings(db)
    journals = {s.sales_journal: "Ventes", s.purchases_journal: "Achats", s.bank_journal: "Banque"}
    accounts = {getattr(s, field): label for field, label in LABELS.items()}
    lines = ["\t".join(FEC_COLUMNS)]
    numbers: dict[tuple[str, str], int] = {}
    for e in page.entries:
        # EcritureNum : numéro continu par journal, une valeur par pièce.
        key = (e.journal, e.piece)
        if key not in numbers:
            numbers[key] = sum(1 for j, _ in numbers if j == e.journal) + 1
        day = e.date.strftime("%Y%m%d")
        lines.append(
            "\t".join(
                [
                    e.journal,
                    journals.get(e.journal, e.journal),
                    f"{e.journal}{numbers[key]:06d}",
                    day,
                    e.account,
                    accounts.get(e.account, e.account),
                    e.aux_account or "",
                    (e.aux_label or "").replace("\t", " "),
                    e.piece,
                    day,
                    e.label.replace("\t", " "),
                    _fr(e.debit),
                    _fr(e.credit),
                    "",
                    "",
                    day,
                    "",
                    "",
                ]
            )  # fmt: skip
        )
    return "\r\n".join(lines) + "\r\n"


def fec_filename(db: Session, company_id: int, end: date) -> str:
    company = org.get_company(db, company_id)
    return f"{company.siren or '000000000'}FEC{end.strftime('%Y%m%d')}.txt"
