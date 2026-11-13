"""Tests du module achats : dépôts, commandes, validation, PDF, accusé, réceptions."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.purchasing.service import line_total
from app.shared.validators import gln_is_valid
from tests.test_admin_utilisateurs import login, monde, uid  # noqa: F401  (fixture)
from tests.test_catalogue import ean


def test_calcul_ligne_et_gln():
    assert line_total(Decimal("3"), Decimal("65.4"), Decimal("0")) == Decimal("196.20")
    assert line_total(Decimal("4"), Decimal("0.0350"), Decimal("10")) == Decimal("0.13")
    assert line_total(Decimal("1"), Decimal("10.005"), Decimal("0")) == Decimal(
        "10.01"
    )  # arrondi commercial
    assert gln_is_valid("3012345000000") and not gln_is_valid("3012345000001")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _setup(client, su, s):
    supplier = client.post(
        "/partners",
        headers=su,
        json={
            "name": f"Fourn achats {s}",
            "min_order_amount": "200",
            "free_shipping_amount": "500",
            "payment_days": 45,
            "payment_end_of_month": True,
            "payment_method": "virement",
        },
    ).json()["id"]
    client.post(
        f"/partners/{supplier}/addresses",
        headers=su,
        json={
            "kind": "commande",
            "line1": "1 rue du Pneu",
            "postal_code": "63000",
            "city": "Clermont",
        },
    )
    article = client.post(
        "/catalog/articles",
        headers=su,
        json={
            "kind": "pneu",
            "ean": ean(s),
            "brand": "Michelin",
            "tire": {
                "width": "205",
                "aspect_ratio": 55,
                "rim": "16",
                "load_index": "91",
                "speed_index": "V",
            },
        },
    ).json()["id"]
    client.post(
        f"/catalog/articles/{article}/suppliers",
        headers=su,
        json={"partner_id": supplier, "purchase_price": "65.40", "supplier_ref": f"MI{s}"},
    )
    other = client.post(
        "/catalog/articles", headers=su, json={"kind": "piece", "designation": "Valve"}
    ).json()["id"]
    return supplier, article, other


def gln(seed: int) -> str:
    body = f"30{seed % 10**10:010d}"
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return body + str((10 - total % 10) % 10)


def _site(client, headers, code="DEP1", gln=None):
    r = client.post(
        "/org/sites",
        headers=headers,
        json={
            "code": code,
            "name": f"Dépôt {code}",
            "address_line1": "ZI Nord",
            "postal_code": "69000",
            "city": "Lyon",
            "gln": gln,
            "delivery_notes": "Réception 8h-12h, quai 3",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.db
def test_cycle_commande(client, monde):  # noqa: F811
    su = monde["su"]
    s = int(uid(), 16) % 10**8
    supplier, article, other = _setup(client, su, s)

    # Sans dépôt : impossible de commander (sauf si un dépôt existe déjà dans la société A).
    sites = client.get("/org/sites", headers=su).json()
    if not sites:
        r = client.post("/purchasing/orders", headers=su, json={"partner_id": supplier})
        assert r.status_code == 422 and "dépôt" in r.json()["error"]["message"]
    site = _site(client, su, f"D{s % 10**6}", gln=gln(s))
    base = {"name": "Autre", "address_line1": "x", "postal_code": "1", "city": "y"}
    assert (
        client.post(
            "/org/sites",
            headers=su,
            json={**base, "code": "X", "gln": gln(s)[:-1] + str((int(gln(s)[-1]) + 1) % 10)},
        ).status_code
        == 422
    )

    r = client.post("/org/sites", headers=su, json={**base, "code": "Y", "gln": gln(s)})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "gln_existant")

    # Brouillon : pas encore de numéro.
    r = client.post(
        "/purchasing/orders",
        headers=su,
        json={
            "partner_id": supplier,
            "site_id": site["id"],
            "expected_date": str(date.today() + timedelta(days=3)),
        },
    )
    assert r.status_code == 201, r.text
    order = r.json()
    assert (order["status"], order["number"]) == ("brouillon", None)
    oid = order["id"]
    assert order["supplier"]["payment_terms"] == "45 jours fin de mois, par virement"

    # Ligne article : prix et référence repris du catalogue, désignation avec la marque.
    order = client.post(
        f"/purchasing/orders/{oid}/lines", headers=su, json={"article_id": article, "quantity": "2"}
    ).json()
    line = order["lines"][0]
    assert (Decimal(line["unit_price"]), line["supplier_ref"]) == (Decimal("65.4"), f"MI{s}")
    assert line["designation"].startswith("MICHELIN 205/55 R16 91V")
    assert Decimal(order["total_ht"]) == Decimal("130.80")
    assert any("Minimum de commande" in w for w in order["warnings"])
    assert any("il manque 369.20" in w for w in order["warnings"])
    # Article non référencé et sans prix : refusé ; avec un prix : accepté, avec alerte.
    r = client.post(
        f"/purchasing/orders/{oid}/lines", headers=su, json={"article_id": other, "quantity": "4"}
    )
    assert r.status_code == 422 and "Prix inconnu" in r.json()["error"]["message"]
    order = client.post(
        f"/purchasing/orders/{oid}/lines",
        headers=su,
        json={"article_id": other, "quantity": "4", "unit_price": "1.25", "discount_pct": "10"},
    ).json()
    assert any("non référencé" in w for w in order["warnings"])
    # Ligne libre (port).
    order = client.post(
        f"/purchasing/orders/{oid}/lines",
        headers=su,
        json={"designation": "Frais de port", "quantity": "1", "unit_price": "15"},
    ).json()
    assert [x["line_no"] for x in order["lines"]] == [1, 2, 3]
    # Modifier la quantité, supprimer la 2e ligne : renumérotation.
    first = order["lines"][0]
    order = client.put(
        f"/purchasing/orders/{oid}/lines/{first['id']}",
        headers=su,
        json={"article_id": article, "quantity": "5"},
    ).json()
    order = client.delete(
        f"/purchasing/orders/{oid}/lines/{order['lines'][1]['id']}", headers=su
    ).json()
    assert [x["line_no"] for x in order["lines"]] == [1, 2]
    assert Decimal(order["total_ht"]) == Decimal("342.00")  # 5 × 65,40 + 15

    # Seuil de validation à 300 € ; un acheteur sans le droit « valider » soumet.
    assert (
        client.put(
            "/purchasing/settings",
            headers=su,
            json={"approval_threshold": "300", "order_footer": "CGA disponibles sur demande."},
        ).status_code
        == 200
    )
    buyer_id = monde["gestionnaire"]["id"]
    r = client.put(
        f"/auth/users/{buyer_id}/companies/{monde['a']}/permissions",
        headers=su,
        json={"permissions": ["purchasing:read", "purchasing:manage"]},
    )
    assert r.status_code == 200, r.text
    buyer = login(client, monde["gestionnaire"]["email"], monde["a"])
    order = client.post(
        f"/purchasing/orders/{oid}/submit", headers=buyer, json={"version": order["version"]}
    ).json()
    assert (order["status"], order["number"]) == ("a_valider", None)
    assert (
        client.post(
            f"/purchasing/orders/{oid}/approve", headers=buyer, json={"version": order["version"]}
        ).status_code
        == 403
    )
    # Refus avec motif → retour en brouillon ; nouvelle soumission ; approbation.
    order = client.post(
        f"/purchasing/orders/{oid}/reject", headers=su, json={"reason": "Trop cher"}
    ).json()
    assert (order["status"], order["rejection_reason"]) == ("brouillon", "Trop cher")
    order = client.post(
        f"/purchasing/orders/{oid}/submit", headers=buyer, json={"version": order["version"]}
    ).json()
    order = client.post(
        f"/purchasing/orders/{oid}/approve", headers=su, json={"version": order["version"]}
    ).json()
    assert order["status"] == "validee" and order["number"].startswith(f"CF-{date.today().year}-")
    assert order["order_date"] == str(date.today())
    # Validée : plus de modification des lignes.
    r = client.post(
        f"/purchasing/orders/{oid}/lines",
        headers=su,
        json={"designation": "X", "quantity": "1", "unit_price": "1"},
    )
    assert (r.status_code, r.json()["error"]["code"]) == (409, "statut_incompatible")

    # PDF.
    r = client.get(f"/purchasing/orders/{oid}/pdf", headers=su)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF") and len(r.content) > 2000

    # Envoyée → accusé du fournisseur.
    order = client.post(f"/purchasing/orders/{oid}/send", headers=buyer).json()
    assert order["status"] == "envoyee"
    l1, l2 = order["lines"]
    later = str(date.today() + timedelta(days=5))
    order = client.post(
        f"/purchasing/orders/{oid}/acknowledge",
        headers=buyer,
        json={
            "supplier_reference": "AR-998",
            "lines": [{"line_id": l1["id"], "confirmed_qty": "4", "confirmed_date": later}],
        },
    ).json()
    assert (order["status"], order["supplier_reference"]) == ("confirmee", "AR-998")
    assert Decimal(order["lines"][0]["confirmed_qty"]) == 4

    # Réception partielle, réception en trop refusée, puis solde.
    r = client.post(
        f"/purchasing/orders/{oid}/receive",
        headers=buyer,
        json={
            "received_on": str(date.today()),
            "delivery_note": "BL-1",
            "lines": [{"line_id": l1["id"], "quantity": "3"}],
        },
    )
    order = r.json()
    assert order["status"] == "partielle" and order["receptions"][0]["number"].startswith("BR-")
    r = client.post(
        f"/purchasing/orders/{oid}/receive",
        headers=buyer,
        json={"received_on": str(date.today()), "lines": [{"line_id": l1["id"], "quantity": "3"}]},
    )
    assert r.status_code == 422 and "reste à recevoir de 2" in r.json()["error"]["message"]
    assert (
        client.post(
            f"/purchasing/orders/{oid}/cancel", headers=buyer, json={"reason": "x"}
        ).status_code
        == 409
    )
    order = client.post(
        f"/purchasing/orders/{oid}/receive",
        headers=buyer,
        json={
            "received_on": str(date.today()),
            "delivery_note": "BL-2",
            "lines": [
                {"line_id": l1["id"], "quantity": "2"},
                {"line_id": l2["id"], "quantity": "1"},
            ],
        },
    ).json()
    assert order["status"] == "recue" and len(order["receptions"]) == 2

    # Liste : groupes, recherche par fournisseur.
    page = client.get(f"/purchasing/orders?group=terminees&q=achats {s}", headers=su).json()
    assert [x["id"] for x in page["items"]] == [oid] and page["items"][0]["received_ratio"] == 1.0
    # Le dépôt est utilisé : suppression refusée.
    assert client.delete(f"/org/sites/{site['id']}", headers=su).status_code == 409

    # Société B : rien de visible.
    in_b = {**su, "X-Company-Id": str(monde["b"])}
    assert client.get(f"/purchasing/orders/{oid}", headers=in_b).status_code == 404
    client.put("/purchasing/settings", headers=su, json={"approval_threshold": None})


@pytest.mark.db
def test_brouillon_annulation_cloture(client, monde):  # noqa: F811
    su = monde["su"]
    s = int(uid(), 16) % 10**8
    supplier, article, _ = _setup(client, su, s)
    if not client.get("/org/sites?active=true", headers=su).json():
        _site(client, su, f"E{s % 10**6}")

    def new_order(qty="10"):
        o = client.post("/purchasing/orders", headers=su, json={"partner_id": supplier}).json()
        return client.post(
            f"/purchasing/orders/{o['id']}/lines",
            headers=su,
            json={"article_id": article, "quantity": qty},
        ).json()

    # Brouillon vide : validation refusée ; brouillon supprimable.
    empty = client.post("/purchasing/orders", headers=su, json={"partner_id": supplier}).json()
    r = client.post(
        f"/purchasing/orders/{empty['id']}/submit", headers=su, json={"version": empty["version"]}
    )
    assert r.status_code == 422
    assert client.delete(f"/purchasing/orders/{empty['id']}", headers=su).status_code == 204
    # PDF indisponible avant validation.
    draft = new_order()
    assert client.get(f"/purchasing/orders/{draft['id']}/pdf", headers=su).status_code == 422
    # Sans seuil : validée directement ; numéros consécutifs.
    a = client.post(
        f"/purchasing/orders/{draft['id']}/submit", headers=su, json={"version": draft["version"]}
    ).json()
    b = new_order()
    b = client.post(
        f"/purchasing/orders/{b['id']}/submit", headers=su, json={"version": b["version"]}
    ).json()
    assert int(b["number"][-5:]) == int(a["number"][-5:]) + 1
    # Une commande validée ne se supprime pas : elle s'annule (avec motif).
    assert client.delete(f"/purchasing/orders/{a['id']}", headers=su).status_code == 409
    a = client.post(
        f"/purchasing/orders/{a['id']}/cancel", headers=su, json={"reason": "Doublon"}
    ).json()
    assert (a["status"], a["cancel_reason"]) == ("annulee", "Doublon")
    # Réception partielle puis clôture (le reliquat ne viendra pas).
    client.post(f"/purchasing/orders/{b['id']}/send", headers=su)
    b = client.post(
        f"/purchasing/orders/{b['id']}/receive",
        headers=su,
        json={
            "received_on": str(date.today()),
            "lines": [{"line_id": b["lines"][0]["id"], "quantity": "6"}],
        },
    ).json()
    b = client.post(
        f"/purchasing/orders/{b['id']}/close", headers=su, json={"reason": "Rupture fabricant"}
    ).json()
    assert b["status"] == "cloturee"
    # Verrouillage optimiste.
    c = new_order()
    r = client.post(
        f"/purchasing/orders/{c['id']}/submit", headers=su, json={"version": c["version"] - 1}
    )
    assert r.status_code == 409
