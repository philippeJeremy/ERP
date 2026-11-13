"""Tests du module ventes : clients, tarif et remises, devis, commande (réservation),
livraison (sortie FIFO par DOT), encours, droits."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.test_achats import _setup, _site
from tests.test_admin_utilisateurs import login, monde, uid  # noqa: F401  (fixture)

TODAY = str(date.today())


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def D(value) -> Decimal:
    return Decimal(str(value))


def ok(r, code=200):
    assert r.status_code == code, r.text
    return r.json()


def _stock(client, su, site, article, qty, dot, cost):
    quai = client.get(f"/inventory/sites/{site}/locations", headers=su).json()[0]
    ok(
        client.post(
            "/inventory/adjustments",
            headers=su,
            json={
                "article_id": article,
                "location_id": quai["id"],
                "dot": dot,
                "quantity": str(qty),
                "reason": "erreur",
                "unit_cost": str(cost),
            },
        ),
        201,
    )


def _available(client, su, article):
    stock = ok(client.get(f"/inventory/articles/{article}", headers=su))
    return D(stock["quantity"]), D(stock["reserved"])


@pytest.mark.db
def test_cycle_vente(client, monde):  # noqa: F811
    su = monde["su"]
    s = int(uid(), 16) % 10**8
    _, tire, valve = _setup(client, su, s)
    site = _site(client, su, f"V{s % 10**6}")["id"]

    # --- Clients : un garage (remise 5 %, 12 % sur les pneus, encours 1 000 €) et un
    # particulier (immatriculation normalisée).
    garage = ok(
        client.post(
            "/partners",
            headers=su,
            json={
                "name": f"Garage Martin {s}",
                "is_supplier": False,
                "is_customer": True,
                "discount_pct": "5",
                "discount_tire_pct": "12",
                "credit_limit": "1000",
                "customer_payment_days": 30,
                "customer_payment_method": "lcr",
            },
        ),
        201,
    )
    assert garage["customer_kind"] == "pro"
    ok(
        client.post(
            f"/partners/{garage['id']}/addresses",
            headers=su,
            json={
                "kind": "facturation",
                "line1": "2 av. Foch",
                "postal_code": "69006",
                "city": "Lyon",
            },
        ),
        201,
    )
    particulier = ok(
        client.post(
            "/partners",
            headers=su,
            json={
                "name": "DUPONT",
                "first_name": "Jean",
                "is_supplier": False,
                "is_customer": True,
                "customer_kind": "particulier",
                "vehicle_registration": "ab 123 cd",
            },
        ),
        201,
    )
    assert particulier["vehicle_registration"] == "AB-123-CD"
    customers = ok(client.get("/partners?role=customer", headers=su))
    assert {garage["id"], particulier["id"]} <= {x["id"] for x in customers["items"]}

    # --- Stock : 2 pneus DOT 2324 à 60 €, 6 pneus DOT 0125 à 70 € → CMP 67,50.
    _stock(client, su, site, tire, 2, "2324", 60)
    _stock(client, su, site, tire, 6, "0125", 70)
    _stock(client, su, site, valve, 100, "", "0.20")

    # --- Devis : sans tarif, impossible d'ajouter l'article sans saisir un prix.
    quote = ok(
        client.post(
            "/sales/quotes", headers=su, json={"customer_id": garage["id"], "site_id": site}
        ),
        201,
    )
    assert quote["number"].startswith(f"DV-{date.today().year}-") and quote["status"] == "brouillon"
    r = client.post(
        f"/sales/quotes/{quote['id']}/lines", headers=su, json={"article_id": tire, "quantity": "4"}
    )
    assert r.status_code == 422 and "Pas de prix de vente" in r.json()["error"]["message"]

    ok(
        client.put(
            f"/sales/prices/{tire}", headers=su, json={"sale_price": "110", "eco_fee": "1.40"}
        )
    )
    row = ok(client.put(f"/sales/prices/{valve}", headers=su, json={"sale_price": "1.50"}))
    assert D(row["average_cost"]) == D("0.20")
    prices = ok(client.get("/sales/prices", headers=su))
    assert {x["article"]["id"] for x in prices["items"]} >= {tire, valve}
    tire_row = next(x for x in prices["items"] if x["article"]["id"] == tire)
    assert D(tire_row["margin_pct"]) == D("38.64")  # (110 − 67,50) / 110
    pricing = ok(
        client.get(
            f"/sales/pricing?customer_id={garage['id']}&article_id={tire}&site_id={site}",
            headers=su,
        )
    )
    assert (D(pricing["discount_pct"]), D(pricing["net_price"]), D(pricing["available"])) == (
        12,
        D("96.80"),
        8,
    )

    qid = quote["id"]
    ok(
        client.post(
            f"/sales/quotes/{qid}/lines", headers=su, json={"article_id": tire, "quantity": "4"}
        )
    )
    ok(
        client.post(
            f"/sales/quotes/{qid}/lines",
            headers=su,
            json={"designation": "Montage + équilibrage", "quantity": "4", "unit_price": "12.50"},
        )
    )
    quote = ok(
        client.post(
            f"/sales/quotes/{qid}/lines", headers=su, json={"article_id": valve, "quantity": "4"}
        )
    )
    tire_line, labour, valve_line = quote["lines"]
    assert (
        D(tire_line["discount_pct"]),
        D(tire_line["line_total"]),
        D(tire_line["eco_total"]),
    ) == (12, D("387.20"), D("5.60"))
    assert (D(valve_line["discount_pct"]), D(valve_line["line_total"])) == (
        5,
        D("5.70"),
    )  # remise générale
    assert labour["article"] is None and D(labour["vat_rate"]) == 20
    # 387,20 + 5,60 + 50,00 + 5,70 = 448,50 HT ; TVA 89,70 ; TTC 538,20.
    totals = [D(quote[k]) for k in ("total_ht", "total_eco", "total_vat", "total_ttc")]
    assert totals == [D("448.50"), D("5.60"), D("89.70"), D("538.20")]
    assert D(quote["margin"]) == D("122.10")  # 387,20 − 4 × 67,50 + 5,70 − 4 × 0,20

    r = client.post(
        f"/sales/quotes/{qid}/lines", headers=su, json={"quantity": "1", "unit_price": "5"}
    )
    assert r.status_code == 422  # ligne libre sans désignation
    quote = ok(client.post(f"/sales/quotes/{qid}/send", headers=su))
    assert quote["status"] == "envoye" and not quote["expired"]
    r = client.post(
        f"/sales/quotes/{qid}/lines", headers=su, json={"article_id": valve, "quantity": "1"}
    )
    assert (r.status_code, r.json()["error"]["code"]) == (409, "statut_incompatible")
    r = client.get(f"/sales/quotes/{qid}/pdf", headers=su)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")

    # --- Accord : commande confirmée, stock réservé.
    order = ok(
        client.post(f"/sales/quotes/{qid}/accept", headers=su, json={"version": quote["version"]})
    )
    assert order["number"].startswith("CC-") and order["status"] == "confirmee"
    assert (
        order["quote"]["number"] == quote["number"] and "Garage Martin" in order["delivery_address"]
    )
    assert D(order["credit"]["outstanding"]) == D("538.20")
    assert ok(client.get(f"/sales/quotes/{qid}", headers=su))["order"]["id"] == order["id"]
    assert _available(client, su, tire) == (8, 4)
    stock = ok(client.get(f"/inventory/stock?site_id={site}&q=valve", headers=su))
    assert (D(stock["items"][0]["reserved"]), D(stock["items"][0]["available"])) == (4, 96)
    r = client.delete(f"/sales/orders/{order['id']}", headers=su)
    assert r.status_code == 409  # pas en brouillon

    # --- Deuxième commande, directe : 6 pneus → encours dépassé (538,20 + 6 × 98,20 × 1,2).
    second = ok(
        client.post(
            "/sales/orders", headers=su, json={"customer_id": garage["id"], "site_id": site}
        ),
        201,
    )
    second = ok(
        client.post(
            f"/sales/orders/{second['id']}/lines",
            headers=su,
            json={"article_id": tire, "quantity": "6", "dot": "0125"},
        )
    )
    r = client.post(
        f"/sales/orders/{second['id']}/confirm", headers=su, json={"version": second["version"]}
    )
    assert (r.status_code, r.json()["error"]["code"]) == (409, "encours_depasse")
    second = ok(
        client.post(
            f"/sales/orders/{second['id']}/confirm",
            headers=su,
            json={"version": second["version"], "force": True},
        )
    )
    assert second["status"] == "confirmee"
    assert _available(client, su, tire) == (8, 10)  # 2 promis de plus que le stock : rupture

    # --- Livraison partielle de la première : 3 pneus (FIFO : 2 en 2324 puis 1 en 0125).
    lines = {x["line_no"]: x for x in order["lines"]}
    r = client.post(
        f"/sales/orders/{order['id']}/deliver",
        headers=su,
        json={"delivered_on": TODAY, "lines": [{"line_id": lines[1]["id"], "quantity": "5"}]},
    )
    assert r.status_code == 422  # plus que commandé
    order = ok(
        client.post(
            f"/sales/orders/{order['id']}/deliver",
            headers=su,
            json={
                "delivered_on": TODAY,
                "carrier": "Retrait comptoir",
                "lines": [
                    {"line_id": lines[1]["id"], "quantity": "3"},
                    {"line_id": lines[2]["id"], "quantity": "4"},
                    {"line_id": lines[3]["id"], "quantity": "4"},
                ],
            },
        )
    )
    assert order["status"] == "partielle"
    delivery = order["deliveries"][0]
    assert delivery["number"].startswith("BL-")
    tire_lots = sorted((x["dot"], D(x["quantity"])) for x in delivery["lines"] if x["line_no"] == 1)
    assert tire_lots == [("0125", 1), ("2324", 2)]
    assert _available(client, su, tire) == (5, 7)  # reste 1 + 6
    moves = ok(client.get(f"/inventory/moves?kind=livraison&article_id={tire}", headers=su))
    assert moves["total"] == 2 and {m["reference"] for m in moves["items"]} == {delivery["number"]}
    assert D(moves["items"][0]["unit_cost"]) == D("67.5000")
    r = client.get(f"/sales/deliveries/{delivery['id']}/pdf", headers=su)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")

    # --- La deuxième ne peut pas partir en entier : 5 en stock (dont 5 en DOT 0125), 6 demandés.
    sl = second["lines"][0]
    r = client.post(
        f"/sales/orders/{second['id']}/deliver",
        headers=su,
        json={"delivered_on": TODAY, "lines": [{"line_id": sl["id"], "quantity": "6"}]},
    )
    assert (r.status_code, r.json()["error"]["code"]) == (409, "stock_insuffisant")
    assert len(ok(client.get(f"/sales/orders/{second['id']}", headers=su))["deliveries"]) == 0

    # --- Solde de la première (reliquat abandonné) et annulation de la deuxième.
    order = ok(
        client.post(
            f"/sales/orders/{order['id']}/close", headers=su, json={"reason": "Client parti"}
        )
    )
    assert order["status"] == "cloturee"
    assert _available(client, su, tire) == (5, 6)
    second = ok(
        client.post(f"/sales/orders/{second['id']}/cancel", headers=su, json={"reason": "Doublon"})
    )
    assert second["status"] == "annulee"
    assert _available(client, su, tire) == (5, 0)

    # --- Devis refusé puis rouvert ; commande brouillon supprimable.
    other = ok(
        client.post(
            "/sales/quotes", headers=su, json={"customer_id": particulier["id"], "site_id": site}
        ),
        201,
    )
    ok(
        client.post(
            f"/sales/quotes/{other['id']}/lines",
            headers=su,
            json={"article_id": tire, "quantity": "2"},
        )
    )
    other = ok(
        client.post(f"/sales/quotes/{other['id']}/refuse", headers=su, json={"reason": "Trop cher"})
    )
    assert other["status"] == "refuse"
    assert D(other["lines"][0]["discount_pct"]) == 0  # pas de remise pour ce client
    assert (
        ok(client.post(f"/sales/quotes/{other['id']}/reopen", headers=su))["status"] == "brouillon"
    )
    draft = ok(
        client.post("/sales/orders", headers=su, json={"customer_id": particulier["id"]}), 201
    )
    assert client.delete(f"/sales/orders/{draft['id']}", headers=su).status_code == 204

    activity = ok(client.get(f"/sales/customers/{garage['id']}/activity", headers=su))
    assert D(activity["credit"]["outstanding"]) == 0 and len(activity["orders"]) == 2
    page = ok(client.get(f"/sales/quotes?q=Martin {s}", headers=su))
    assert [x["id"] for x in page["items"]] == [qid]
    assert ok(client.get("/sales/orders?open=true", headers=su))["total"] == 0

    # --- Société B : rien de visible.
    in_b = {**su, "X-Company-Id": str(monde["b"])}
    assert ok(client.get("/sales/quotes", headers=in_b))["total"] == 0
    assert client.get(f"/sales/orders/{order['id']}", headers=in_b).status_code == 404


@pytest.mark.db
def test_droits_ventes(client, monde):  # noqa: F811
    su = monde["su"]
    customer = ok(
        client.post(
            "/partners",
            headers=su,
            json={"name": "Client droits", "is_supplier": False, "is_customer": True},
        ),
        201,
    )
    user_id = monde["gestionnaire"]["id"]
    client.put(
        f"/auth/users/{user_id}/companies/{monde['a']}/permissions",
        headers=su,
        json={"permissions": ["sales:read", "sales:manage"]},
    )
    seller = login(client, monde["gestionnaire"]["email"], monde["a"])
    quote = client.post("/sales/quotes", headers=seller, json={"customer_id": customer["id"]})
    assert quote.status_code in (201, 422)  # 422 s'il n'y a aucun dépôt dans la société
    assert (
        client.put("/sales/prices/1", headers=seller, json={"sale_price": "1"}).status_code == 403
    )
    assert (
        client.post(
            "/sales/orders/1/deliver",
            headers=seller,
            json={"delivered_on": TODAY, "lines": [{"line_id": 1, "quantity": "1"}]},
        ).status_code
        == 403
    )
    lecteur = login(client, monde["lecteur"]["email"], monde["a"])
    assert client.get("/sales/quotes", headers=lecteur).status_code == 403
