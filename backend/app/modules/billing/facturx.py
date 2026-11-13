"""Factur-X : le XML « Cross Industry Invoice » (CII, norme UN/CEFACT D16B) au profil
EN 16931, embarqué dans le PDF de la facture.

Un humain lit le PDF, un logiciel lit le XML : c'est le format hybride retenu pour la
facturation électronique en France (avec UBL et CII purs). La bibliothèque `factur-x`
vérifie le XML contre le schéma XSD officiel et l'attache au PDF.
"""

from decimal import Decimal
from xml.sax.saxutils import escape

from app.modules.billing.invoices import eco_total, vat_rows
from app.modules.billing.models import Invoice

PAYMENT_CODES = {"virement": "30", "prelevement": "59", "cheque": "20", "lcr": "31",
                 "carte": "48", "especes": "10"}  # fmt: skip


def _a(value: Decimal, decimals: int = 2) -> str:
    return f"{value:.{decimals}f}"


def _t(value: str | None) -> str:
    return escape(value or "")


def _date(d) -> str:
    return d.strftime("%Y%m%d")


def _address(lines: list[str], country: str = "FR") -> str:
    """Adresse « ligne 1 / … / CP Ville » → éléments CII (le CP est le premier mot)."""
    lines = [x for x in lines if x]
    postcode, city = "", ""
    if lines:
        last = lines[-1].split(" ", 1)
        postcode, city = (last[0], last[1]) if len(last) == 2 else ("", last[0])
        lines = lines[:-1]
    parts = [f"<ram:PostcodeCode>{_t(postcode)}</ram:PostcodeCode>"] if postcode else []
    if lines:
        parts.append(f"<ram:LineOne>{_t(lines[0])}</ram:LineOne>")
    if len(lines) > 1:
        parts.append(f"<ram:LineTwo>{_t(' '.join(lines[1:]))}</ram:LineTwo>")
    if city:
        parts.append(f"<ram:CityName>{_t(city)}</ram:CityName>")
    parts.append(f"<ram:CountryID>{country}</ram:CountryID>")
    return "<ram:PostalTradeAddress>" + "".join(parts) + "</ram:PostalTradeAddress>"


def build_xml(
    invoice: Invoice, company, payment_method: str | None, original_number: str | None
) -> bytes:
    lines_xml = []
    for line in invoice.lines:
        net = (line.line_total / line.quantity) if line.quantity else Decimal(0)
        product = ""
        if line.ean and len(line.ean) in (8, 12, 13, 14):
            product += f'<ram:GlobalID schemeID="0160">{line.ean}</ram:GlobalID>'
        if line.article_code:
            product += f"<ram:SellerAssignedID>{_t(line.article_code)}</ram:SellerAssignedID>"
        product += f"<ram:Name>{_t(line.designation)}</ram:Name>"
        eco = eco_total(line)
        charge = (
            "<ram:SpecifiedTradeAllowanceCharge><ram:ChargeIndicator><udt:Indicator>true"
            f"</udt:Indicator></ram:ChargeIndicator><ram:ActualAmount>{_a(eco)}</ram:ActualAmount>"
            "<ram:Reason>Eco-contribution</ram:Reason></ram:SpecifiedTradeAllowanceCharge>"
            if eco
            else ""
        )
        lines_xml.append(
            "<ram:IncludedSupplyChainTradeLineItem>"
            f"<ram:AssociatedDocumentLineDocument><ram:LineID>{line.line_no}</ram:LineID>"
            "</ram:AssociatedDocumentLineDocument>"
            f"<ram:SpecifiedTradeProduct>{product}</ram:SpecifiedTradeProduct>"
            "<ram:SpecifiedLineTradeAgreement><ram:NetPriceProductTradePrice>"
            f"<ram:ChargeAmount>{_a(net, 4)}</ram:ChargeAmount>"
            "</ram:NetPriceProductTradePrice></ram:SpecifiedLineTradeAgreement>"
            "<ram:SpecifiedLineTradeDelivery>"
            f'<ram:BilledQuantity unitCode="C62">{_a(line.quantity, 3)}</ram:BilledQuantity>'
            "</ram:SpecifiedLineTradeDelivery>"
            "<ram:SpecifiedLineTradeSettlement><ram:ApplicableTradeTax><ram:TypeCode>VAT"
            "</ram:TypeCode><ram:CategoryCode>S</ram:CategoryCode>"
            f"<ram:RateApplicablePercent>{_a(line.vat_rate)}</ram:RateApplicablePercent>"
            f"</ram:ApplicableTradeTax>{charge}"
            "<ram:SpecifiedTradeSettlementLineMonetarySummation>"
            f"<ram:LineTotalAmount>{_a(line.line_total + eco)}</ram:LineTotalAmount>"
            "</ram:SpecifiedTradeSettlementLineMonetarySummation>"
            "</ram:SpecifiedLineTradeSettlement></ram:IncludedSupplyChainTradeLineItem>"
        )
    company_address = [company.address_line1, company.address_line2,
                       f"{company.postal_code or ''} {company.city or ''}".strip()]  # fmt: skip
    seller = (
        f"<ram:SellerTradeParty><ram:Name>{_t(company.name)}</ram:Name>"
        + (
            f'<ram:SpecifiedLegalOrganization><ram:ID schemeID="0002">{company.siren}</ram:ID>'
            "</ram:SpecifiedLegalOrganization>"
            if company.siren
            else ""
        )
        + _address([x for x in company_address if x], company.country_code or "FR")
        + (
            f'<ram:SpecifiedTaxRegistration><ram:ID schemeID="VA">{_t(company.vat_number)}</ram:ID>'
            "</ram:SpecifiedTaxRegistration>"
            if company.vat_number
            else ""
        )
        + "</ram:SellerTradeParty>"
    )
    buyer = (
        f"<ram:BuyerTradeParty><ram:Name>{_t(invoice.customer_name)}</ram:Name>"
        + (
            f'<ram:SpecifiedLegalOrganization><ram:ID schemeID="0002">{invoice.customer_siren}'
            "</ram:ID></ram:SpecifiedLegalOrganization>"
            if invoice.customer_siren
            else ""
        )
        + _address((invoice.customer_address or "").split("\n"))
        + (
            f'<ram:SpecifiedTaxRegistration><ram:ID schemeID="VA">{_t(invoice.customer_vat)}'
            "</ram:ID></ram:SpecifiedTaxRegistration>"
            if invoice.customer_vat
            else ""
        )
        + "</ram:BuyerTradeParty>"
    )
    taxes = "".join(
        "<ram:ApplicableTradeTax>"
        f"<ram:CalculatedAmount>{_a(r.vat)}</ram:CalculatedAmount><ram:TypeCode>VAT</ram:TypeCode>"
        f"<ram:BasisAmount>{_a(r.base)}</ram:BasisAmount><ram:CategoryCode>S</ram:CategoryCode>"
        f"<ram:RateApplicablePercent>{_a(r.rate)}</ram:RateApplicablePercent>"
        "</ram:ApplicableTradeTax>"
        for r in vat_rows(invoice)
    )
    means = ""
    code = PAYMENT_CODES.get(payment_method or "virement", "30")
    if company.iban and code in ("30", "58"):
        means = (
            f"<ram:SpecifiedTradeSettlementPaymentMeans><ram:TypeCode>{code}</ram:TypeCode>"
            "<ram:PayeePartyCreditorFinancialAccount>"
            f"<ram:IBANID>{_t(company.iban.replace(' ', ''))}</ram:IBANID>"
            "</ram:PayeePartyCreditorFinancialAccount></ram:SpecifiedTradeSettlementPaymentMeans>"
        )
    else:
        means = (
            f"<ram:SpecifiedTradeSettlementPaymentMeans><ram:TypeCode>{code}</ram:TypeCode>"
            "</ram:SpecifiedTradeSettlementPaymentMeans>"
        )
    terms = "<ram:SpecifiedTradePaymentTerms>"
    if invoice.payment_terms:
        terms += f"<ram:Description>{_t(invoice.payment_terms)}</ram:Description>"
    if invoice.due_date:
        terms += (
            '<ram:DueDateDateTime><udt:DateTimeString format="102">'
            f"{_date(invoice.due_date)}</udt:DateTimeString></ram:DueDateDateTime>"
        )
    terms += "</ram:SpecifiedTradePaymentTerms>"
    line_total = sum((x.line_total + eco_total(x) for x in invoice.lines), Decimal(0))
    due = invoice.total_ttc
    summation = (
        "<ram:SpecifiedTradeSettlementHeaderMonetarySummation>"
        f"<ram:LineTotalAmount>{_a(line_total)}</ram:LineTotalAmount>"
        f"<ram:TaxBasisTotalAmount>{_a(invoice.total_ht)}</ram:TaxBasisTotalAmount>"
        f'<ram:TaxTotalAmount currencyID="EUR">{_a(invoice.total_vat)}</ram:TaxTotalAmount>'
        f"<ram:GrandTotalAmount>{_a(invoice.total_ttc)}</ram:GrandTotalAmount>"
        f"<ram:DuePayableAmount>{_a(due)}</ram:DuePayableAmount>"
        "</ram:SpecifiedTradeSettlementHeaderMonetarySummation>"
    )
    referenced = (
        f"<ram:InvoiceReferencedDocument><ram:IssuerAssignedID>{_t(original_number)}"
        "</ram:IssuerAssignedID></ram:InvoiceReferencedDocument>"
        if original_number
        else ""
    )
    delivery = (
        "<ram:ApplicableHeaderTradeDelivery>"
        + (
            '<ram:ActualDeliverySupplyChainEvent><ram:OccurrenceDateTime><udt:DateTimeString format="102">'  # noqa: E501
            f"{_date(invoice.delivery_date)}</udt:DateTimeString></ram:OccurrenceDateTime>"
            "</ram:ActualDeliverySupplyChainEvent>"
            if invoice.delivery_date
            else ""
        )
        + "</ram:ApplicableHeaderTradeDelivery>"
    )
    buyer_ref = (
        f"<ram:BuyerReference>{_t(invoice.customer_reference[:100])}</ram:BuyerReference>"
        if invoice.customer_reference
        else ""
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100" '  # noqa: E501
        'xmlns:qdt="urn:un:unece:uncefact:data:standard:QualifiedDataType:100" '
        'xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100" '  # noqa: E501
        'xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">'
        "<rsm:ExchangedDocumentContext><ram:GuidelineSpecifiedDocumentContextParameter>"
        "<ram:ID>urn:cen.eu:en16931:2017</ram:ID></ram:GuidelineSpecifiedDocumentContextParameter>"
        "</rsm:ExchangedDocumentContext>"
        f"<rsm:ExchangedDocument><ram:ID>{_t(invoice.number)}</ram:ID>"
        f"<ram:TypeCode>{'380' if invoice.kind == 'facture' else '381'}</ram:TypeCode>"
        '<ram:IssueDateTime><udt:DateTimeString format="102">'
        f"{_date(invoice.issue_date)}</udt:DateTimeString></ram:IssueDateTime>"
        + (
            f"<ram:IncludedNote><ram:Content>{_t(invoice.note)}</ram:Content></ram:IncludedNote>"
            if invoice.note
            else ""
        )
        + "</rsm:ExchangedDocument><rsm:SupplyChainTradeTransaction>"
        + "".join(lines_xml)
        + f"<ram:ApplicableHeaderTradeAgreement>{buyer_ref}{seller}{buyer}</ram:ApplicableHeaderTradeAgreement>"  # noqa: E501
        + delivery
        + "<ram:ApplicableHeaderTradeSettlement><ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>"  # noqa: E501
        + means
        + taxes
        + terms
        + summation
        + referenced
        + "</ram:ApplicableHeaderTradeSettlement></rsm:SupplyChainTradeTransaction>"
        "</rsm:CrossIndustryInvoice>"
    )
    return xml.encode("utf-8")
