"""Tests de la facturation : factures depuis les BL, émission, inaltérabilité, Factur-X,
avoirs, règlements et lettrage, retards et relances, encours, factures fournisseur
(rapprochement), export comptable."""

import io
import os
import random
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.core.db import SessionLocal, set_db_context
from app.main import app
from tests.test_achats import _setup, _site
from tests.test_admin_utilisateurs import login, monde, uid  # noqa: F401  (fixture)
from tests.test_stock import _order, _receive

TODAY = date.today()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def D(value) -> Decimal:
    return Decimal(str(value))


def ok(r, code=200):
    assert r.status_code == code, r.text
    return r.json()


def _company_legal(client, su, company_id):
    company = ok(client.get(f"/org/companies/{company_id}", headers=su))
    return ok(
        client.patch(
            f"/org/companies/{company_id}",
            headers=su,
            json={
                "version": company["version"],
                "legal_form": "SAS",
                "share_capital": "50000",
                "siren": f"{random.randint(100000000, 999999999)}",
                "rcs": "RCS Lyon",
                "vat_number": "FR12345678901",
                "address_line1": "1 rue du Test",
                "postal_code": "69001",
                "city": "Lyon",
                "iban": "FR7630006000011234567890189",
                "bic": "AGRIFRPP",
            },
        )
    )


def _sold(client, su, s):
    """Un client, du stock, une commande de 4 pneus + montage livrée en deux fois."""
    supplier, tire, _valve = _setup(client, su, s)
    site = _site(client, su, f"F{s % 10**6}")["id"]
    customer = ok(
        client.post(
            "/partners",
            headers=su,
            json={
                "name": f"Garage Facture {s}",
                "is_supplier": False,
                "is_customer": True,
                "siret": f"{random.randint(10**13, 10**14 - 1)}",
                "vat_number": "FR99887766554",
                "customer_payment_days": 30,
                "customer_payment_method": "virement",
            },
        ),
        201,
    )
    ok(
        client.post(
            f"/partners/{customer['id']}/addresses",
            headers=su,
            json={
                "kind": "facturation",
                "line1": "5 rue Garage",
                "postal_code": "69007",
                "city": "Lyon",
            },
        ),
        201,
    )
    quai = client.get(f"/inventory/sites/{site}/locations", headers=su).json()[0]
    ok(
        client.post(
            "/inventory/adjustments",
            headers=su,
            json={
                "article_id": tire,
                "location_id": quai["id"],
                "dot": "2324",
                "quantity": "10",
                "reason": "erreur",
                "unit_cost": "60",
            },  # fmt: skip
        ),
        201,
    )
    ok(
        client.put(
            f"/sales/prices/{tire}", headers=su, json={"sale_price": "100", "eco_fee": "1.50"}
        )
    )
    order = ok(
        client.post(
            "/sales/orders", headers=su, json={"customer_id": customer["id"], "site_id": site}
        ),
        201,
    )
    ok(
        client.post(
            f"/sales/orders/{order['id']}/lines",
            headers=su,
            json={"article_id": tire, "quantity": "4"},
        )
    )
    order = ok(
        client.post(
            f"/sales/orders/{order['id']}/lines",
            headers=su,
            json={"designation": "Montage", "quantity": "4", "unit_price": "15"},
        )
    )
    order = ok(
        client.post(
            f"/sales/orders/{order['id']}/confirm", headers=su, json={"version": order["version"]}
        )
    )
    tire_line, labour = order["lines"]
    deliver = lambda lines: ok(  # noqa: E731
        client.post(
            f"/sales/orders/{order['id']}/deliver",
            headers=su,
            json={"delivered_on": str(TODAY), "lines": lines},
        )
    )
    deliver(
        [{"line_id": tire_line["id"], "quantity": "2"}, {"line_id": labour["id"], "quantity": "4"}]
    )
    order = deliver([{"line_id": tire_line["id"], "quantity": "2"}])
    return supplier, tire, site, customer, order


@pytest.mark.db
def test_facturation_client(client, monde):  # noqa: F811
    su = monde["su"]
    s = int(uid(), 16) % 10**8
    _, tire, site, customer, order = _sold(client, su, s)
    cid = customer["id"]
    bl1, bl2 = order["deliveries"]

    # --- À facturer : les deux BL du client.
    todo = ok(client.get(f"/billing/to-invoice?customer_id={cid}", headers=su))
    assert [d["number"] for d in todo[0]["deliveries"]] == [bl1["number"], bl2["number"]]
    # 4 × 100 + 4 × 1,50 + 4 × 15 = 466 HT
    assert D(todo[0]["total_ht"]) == D("466.00")

    # --- Facture récapitulative (brouillon) des deux BL.
    drafts = ok(
        client.post(
            "/billing/invoices/from-deliveries",
            headers=su,
            json={"delivery_ids": [bl1["id"], bl2["id"]], "grouping": "recap"},
        )
    )
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft["status"] == "brouillon" and draft["number"] is None
    assert len(draft["lines"]) == 3 and {x["delivery_number"] for x in draft["lines"]} == {
        bl1["number"],
        bl2["number"],
    }
    totals = [D(draft[k]) for k in ("total_ht", "total_eco", "total_vat", "total_ttc")]
    assert totals == [D("466.00"), D("6.00"), D("93.20"), D("559.20")]
    r = client.post(
        "/billing/invoices/from-deliveries", headers=su, json={"delivery_ids": [bl1["id"]]}
    )
    assert (r.status_code, r.json()["error"]["code"]) == (409, "deja_facture")
    assert ok(client.get(f"/billing/to-invoice?customer_id={cid}", headers=su)) == []

    # Brouillon : PDF sans Factur-X ; on peut ajouter une ligne libre puis la retirer.
    r = client.get(f"/billing/invoices/{draft['id']}/pdf", headers=su)
    assert r.status_code == 200 and b"factur-x.xml" not in r.content
    tmp = ok(
        client.post(
            f"/billing/invoices/{draft['id']}/lines",
            headers=su,
            json={"designation": "Frais de port", "quantity": "1", "unit_price": "10"},
        )
    )
    assert D(tmp["total_ttc"]) == D("571.20")
    draft = ok(
        client.delete(f"/billing/invoices/{draft['id']}/lines/{tmp['lines'][-1]['id']}", headers=su)
    )

    # --- Émission : refusée sans mentions légales, puis numéro et échéance à 30 jours.
    company = ok(client.get(f"/org/companies/{monde['a']}", headers=su))
    if not company["siren"]:
        r = client.post(f"/billing/invoices/{draft['id']}/issue", headers=su)
        assert r.status_code == 422 and "Mentions légales" in r.json()["error"]["message"]
    _company_legal(client, su, monde["a"])
    invoice = ok(client.post(f"/billing/invoices/{draft['id']}/issue", headers=su))
    assert invoice["number"].startswith(f"FA-{TODAY.year}-") and invoice["status"] == "emise"
    assert invoice["issue_date"] == str(TODAY) and invoice["due_date"] == str(
        TODAY + timedelta(days=30)
    )
    assert (
        invoice["customer_name"] == f"Garage Facture {s}"
        and "5 rue Garage" in invoice["customer_address"]
    )
    assert invoice["payment_status"] == "a_payer" and D(invoice["balance"]) == D("559.20")
    iid = invoice["id"]

    # Inaltérable : ni l'API ni même une requête SQL ne peuvent la changer.
    r = client.post(
        f"/billing/invoices/{iid}/lines",
        headers=su,
        json={"designation": "x", "quantity": "1", "unit_price": "1"},
    )
    assert r.status_code == 409
    assert client.delete(f"/billing/invoices/{iid}", headers=su).status_code == 409
    with SessionLocal() as db:
        set_db_context(db, user_id=None, company_id=monde["a"])
        with pytest.raises(DBAPIError, match="modification interdite"):
            db.execute(text("UPDATE billing.invoices SET total_ttc = 1 WHERE id = :i"), {"i": iid})
        db.rollback()

    # --- Factur-X : XML EN 16931 valide (schéma XSD officiel), embarqué dans le PDF.
    from facturx import get_facturx_xml_from_pdf, xml_check_xsd

    pdf = client.get(f"/billing/invoices/{iid}/pdf", headers=su)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    filename, xml = get_facturx_xml_from_pdf(io.BytesIO(pdf.content))
    assert filename == "factur-x.xml" and xml_check_xsd(xml, flavor="factur-x", level="en16931")
    assert invoice["number"].encode() in xml and b"<ram:GrandTotalAmount>559.20" in xml
    assert b"urn:cen.eu:en16931:2017" in xml and b'schemeID="0002"' in xml
    raw = client.get(f"/billing/invoices/{iid}/xml", headers=su)
    assert raw.status_code == 200 and raw.content == xml

    # --- Avoir partiel : 1 pneu repris → imputé automatiquement sur la facture.
    tire_line = next(
        x for x in invoice["lines"] if x["article_id"] == tire and D(x["quantity"]) == 2
    )
    r = client.post(
        f"/billing/invoices/{iid}/credit-note",
        headers=su,
        json={
            "lines": [{"line_id": tire_line["id"], "quantity": "3"}],
            "reason": "Pneu défectueux",
        },
    )
    assert r.status_code == 422  # plus que facturé sur cette ligne
    note = ok(
        client.post(
            f"/billing/invoices/{iid}/credit-note",
            headers=su,
            json={
                "lines": [{"line_id": tire_line["id"], "quantity": "1"}],
                "reason": "Pneu défectueux",
            },
        )
    )
    assert note["kind"] == "avoir" and note["original"]["id"] == iid
    assert D(note["total_ttc"]) == D("121.80")  # (100 + 1,50) × 1,2
    note = ok(client.post(f"/billing/invoices/{note['id']}/issue", headers=su))
    assert note["number"].startswith("AV-") and note["payment_status"] == "payee"  # crédit consommé
    invoice = ok(client.get(f"/billing/invoices/{iid}", headers=su))
    assert D(invoice["balance"]) == D("437.40") and invoice["payment_status"] == "partielle"
    assert invoice["credit_notes"][0]["number"] == note["number"]
    assert (
        next(x for x in invoice["lines"] if x["id"] == tire_line["id"])["creditable_qty"] == "1.000"
    )
    _, xml = get_facturx_xml_from_pdf(
        io.BytesIO(client.get(f"/billing/invoices/{note['id']}/pdf", headers=su).content)
    )
    assert b"<ram:TypeCode>381</ram:TypeCode>" in xml and xml_check_xsd(
        xml, flavor="factur-x", level="en16931"
    )

    # --- Règlements : un virement partiel (lettré automatiquement), puis le solde + un trop-perçu.
    pay = ok(
        client.post(
            "/billing/payments",
            headers=su,
            json={
                "customer_id": cid,
                "paid_on": str(TODAY),
                "amount": "200",
                "method": "virement",
                "reference": "VIR 1",
            },
        ),
        201,
    )
    assert pay["number"].startswith("RG-") and D(pay["unallocated"]) == 0
    assert pay["allocations"][0]["invoice_number"] == invoice["number"]
    pay2 = ok(
        client.post(
            "/billing/payments",
            headers=su,
            json={"customer_id": cid, "paid_on": str(TODAY), "amount": "300", "method": "cheque"},
        ),
        201,
    )
    assert D(pay2["unallocated"]) == D("62.60")  # 300 − 237,40
    invoice = ok(client.get(f"/billing/invoices/{iid}", headers=su))
    assert invoice["payment_status"] == "payee" and len(invoice["allocations"]) == 3  # avoir + 2
    account = ok(client.get(f"/billing/customers/{cid}/account", headers=su))
    assert D(account["total_due"]) == 0 and D(account["available_credit"]) == D("62.60")

    # Erreur de saisie : on supprime le chèque, la facture redevient partiellement payée.
    assert client.delete(f"/billing/payments/{pay2['id']}", headers=su).status_code == 204
    invoice = ok(client.get(f"/billing/invoices/{iid}", headers=su))
    assert D(invoice["balance"]) == D("237.40")

    # --- Retard et relance : on vieillit l'échéance (rôle propriétaire, trigger suspendu).
    owner = create_engine(os.environ["TEST_MIGRATION_DATABASE_URL"])
    with owner.begin() as conn:
        conn.execute(text("ALTER TABLE billing.invoices DISABLE TRIGGER protect_issued"))
        conn.execute(
            text("UPDATE billing.invoices SET due_date = :d WHERE id = :i"),
            {"d": TODAY - timedelta(days=40), "i": iid},
        )
        conn.execute(text("ALTER TABLE billing.invoices ENABLE TRIGGER protect_issued"))
    owner.dispose()
    invoice = ok(client.get(f"/billing/invoices/{iid}", headers=su))
    assert invoice["payment_status"] == "en_retard" and invoice["days_late"] == 40
    aging = ok(client.get("/billing/receivables", headers=su))
    row = next(x for x in aging["rows"] if x["customer_id"] == cid)
    assert D(row["late_60"]) == D("237.40") and D(row["total"]) == D("237.40")
    late = ok(client.get(f"/billing/invoices?payment=en_retard&customer_id={cid}", headers=su))
    assert [x["id"] for x in late["items"]] == [iid]
    r = client.post(f"/billing/customers/{cid}/reminder", headers=su)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert ok(client.get(f"/billing/invoices/{iid}", headers=su))["reminder_count"] == 1

    # --- Encours (ventes) : la facture impayée y figure.
    activity = ok(client.get(f"/sales/customers/{cid}/activity", headers=su))
    assert D(activity["credit"]["outstanding"]) == D("237.40")

    # --- Facture libre (prestation) émise, puis supprimer un brouillon.
    free = ok(client.post("/billing/invoices", headers=su, json={"customer_id": cid}), 201)
    free = ok(
        client.post(
            f"/billing/invoices/{free['id']}/lines",
            headers=su,
            json={"designation": "Gardiennage pneus hiver", "quantity": "1", "unit_price": "40"},
        )
    )
    assert D(free["total_ttc"]) == D("48.00")
    assert client.delete(f"/billing/invoices/{free['id']}", headers=su).status_code == 204

    # --- Export comptable du jour : équilibré.
    entries = ok(client.get(f"/billing/accounting/entries?start={TODAY}&end={TODAY}", headers=su))
    assert D(entries["total_debit"]) == D(entries["total_credit"]) > 0
    sale = [e for e in entries["entries"] if e["piece"] == invoice["number"]]
    assert {e["account"] for e in sale} == {"411000", "707000", "706000", "708500", "445710"}
    assert D(next(e for e in sale if e["account"] == "411000")["debit"]) == D("559.20")
    assert D(next(e for e in sale if e["account"] == "708500")["credit"]) == D("6.00")
    fec = client.get(f"/billing/accounting/fec?start={TODAY}&end={TODAY}", headers=su)
    assert fec.status_code == 200 and fec.text.startswith("JournalCode\tJournalLib\tEcritureNum")
    assert "FEC" in fec.headers["content-disposition"]
    csv = client.get(f"/billing/accounting/export.csv?start={TODAY}&end={TODAY}", headers=su)
    assert csv.status_code == 200 and invoice["number"] in csv.text

    # --- Société B : rien.
    in_b = {**su, "X-Company-Id": str(monde["b"])}
    assert ok(client.get("/billing/invoices", headers=in_b))["total"] == 0


@pytest.mark.db
def test_factures_fournisseur(client, monde):  # noqa: F811
    su = monde["su"]
    s = int(uid(), 16) % 10**8
    supplier, tire, _ = _setup(client, su, s)
    site = _site(client, su, f"G{s % 10**6}")["id"]
    order = _order(client, su, supplier, site, [(tire, 10, "70", 0)])
    line = order["lines"][0]
    ok(_receive(client, su, order, [{"line_id": line["id"], "quantity": "6", "dot": "2324"}]))

    todo = ok(client.get(f"/billing/suppliers/{supplier}/to-invoice", headers=su))
    assert len(todo) == 1 and D(todo[0]["total_ht"]) == D("420.00")

    # Le fournisseur facture 6 pneus à 72 € (au lieu de 70) : écart de prix.
    invoice = ok(
        client.post(
            "/billing/supplier-invoices",
            headers=su,
            json={
                "partner_id": supplier,
                "supplier_number": f"F-{s}",
                "invoice_date": str(TODAY),
                "total_ht": "432",
                "total_vat": "86.40",
                "total_ttc": "518.40",
                "reception_ids": [todo[0]["id"]],
            },  # fmt: skip
        ),
        201,
    )
    assert invoice["number"].startswith("FF-") and invoice["status"] == "brouillon"
    # Fournisseur à 45 jours fin de mois (voir _setup).
    assert invoice["due_date"] >= str(TODAY + timedelta(days=45))
    assert any("Total HT saisi 432.00" in g for g in invoice["gaps"])
    sl = invoice["lines"][0]
    assert (D(sl["expected_quantity"]), D(sl["expected_price"])) == (6, D("70.0000"))
    invoice = ok(
        client.put(
            f"/billing/supplier-invoices/{invoice['id']}/lines/{sl['id']}",
            headers=su,
            json={"quantity": "6", "unit_price": "72"},
        )
    )
    assert len(invoice["gaps"]) == 1 and "prix facturé 72" in invoice["gaps"][0]
    assert ok(client.get(f"/billing/suppliers/{supplier}/to-invoice", headers=su)) == []

    r = client.post(
        f"/billing/supplier-invoices/{invoice['id']}/approve",
        headers=su,
        json={"version": invoice["version"]},
    )
    assert (r.status_code, r.json()["error"]["code"]) == (409, "ecarts")
    r = client.post(
        "/billing/supplier-invoices",
        headers=su,
        json={
            "partner_id": supplier,
            "supplier_number": f"F-{s}",
            "invoice_date": str(TODAY),
            "total_ht": "1",
            "total_vat": "0",
            "total_ttc": "1",
        },  # fmt: skip
    )
    assert (r.status_code, r.json()["error"]["code"]) == (409, "doublon")
    invoice = ok(
        client.post(
            f"/billing/supplier-invoices/{invoice['id']}/approve",
            headers=su,
            json={
                "version": invoice["version"],
                "note": "Hausse tarifaire acceptée par l'acheteur",
            },
        )
    )
    assert invoice["status"] == "bon_a_payer" and invoice["approval_note"].startswith("Hausse")
    r = client.put(
        f"/billing/supplier-invoices/{invoice['id']}/lines/{sl['id']}",
        headers=su,
        json={"quantity": "1", "unit_price": "1"},
    )
    assert r.status_code == 409
    r = client.post(
        f"/billing/supplier-invoices/{invoice['id']}/payments",
        headers=su,
        json={"paid_on": str(TODAY), "amount": "600", "method": "virement"},
    )
    assert r.status_code == 422
    invoice = ok(
        client.post(
            f"/billing/supplier-invoices/{invoice['id']}/payments",
            headers=su,
            json={"paid_on": str(TODAY), "amount": "518.40", "method": "virement"},
        )
    )
    assert D(invoice["balance"]) == 0
    assert ok(client.get("/billing/supplier-invoices?unpaid=true", headers=su))["total"] == 0

    entries = ok(client.get(f"/billing/accounting/entries?start={TODAY}&end={TODAY}", headers=su))
    purchase = [e for e in entries["entries"] if e["piece"] == invoice["number"]]
    assert {(e["account"], e["debit"], e["credit"]) for e in purchase} == {
        ("607000", "432.00", "0.00"), ("445660", "86.40", "0.00"), ("401000", "0.00", "518.40"),
    }  # fmt: skip
    assert D(entries["total_debit"]) == D(entries["total_credit"])

    # Droits : un lecteur facturation ne peut ni émettre ni saisir.
    user_id = monde["gestionnaire"]["id"]
    client.put(
        f"/auth/users/{user_id}/companies/{monde['a']}/permissions",
        headers=su,
        json={"permissions": ["billing:read"]},
    )
    reader = login(client, monde["gestionnaire"]["email"], monde["a"])
    assert client.get("/billing/invoices", headers=reader).status_code == 200
    assert client.post("/billing/invoices/1/issue", headers=reader).status_code == 403
    assert (
        client.get(f"/billing/accounting/fec?start={TODAY}&end={TODAY}", headers=reader).status_code
        == 403
    )
