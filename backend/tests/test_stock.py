"""Tests du module stock : réception → stock par DOT, CMP, ajustements, transferts,
inventaires, emplacements, droits et journal inaltérable."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.core.db import SessionLocal, set_db_context
from app.main import app
from tests.test_achats import _setup, _site
from tests.test_admin_utilisateurs import login, monde, uid  # noqa: F401  (fixture)

TODAY = str(date.today())


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def D(value) -> Decimal:
    return Decimal(str(value))


def _order(client, su, supplier, site_id, lines):
    """Commande validée et envoyée ; `lines` = [(article, quantité, prix, remise)]."""
    oid = client.post(
        "/purchasing/orders", headers=su, json={"partner_id": supplier, "site_id": site_id}
    ).json()["id"]
    for article, qty, price, discount in lines:
        r = client.post(
            f"/purchasing/orders/{oid}/lines",
            headers=su,
            json={
                "article_id": article,
                "quantity": str(qty),
                "unit_price": str(price),
                "discount_pct": str(discount),
            },
        )
        assert r.status_code == 200, r.text
    order = r.json()
    order = client.post(
        f"/purchasing/orders/{oid}/submit", headers=su, json={"version": order["version"]}
    ).json()
    assert order["status"] == "validee", order
    return client.post(f"/purchasing/orders/{oid}/send", headers=su).json()


def _receive(client, su, order, lines):
    r = client.post(
        f"/purchasing/orders/{order['id']}/receive",
        headers=su,
        json={"received_on": TODAY, "delivery_note": "BL", "lines": lines},
    )
    return r


@pytest.mark.db
def test_stock_complet(client, monde):  # noqa: F811
    su = monde["su"]
    s = int(uid(), 16) % 10**8
    supplier, article, valve = _setup(client, su, s)
    lyon = _site(client, su, f"L{s % 10**6}")
    paris = _site(client, su, f"P{s % 10**6}")

    # --- Emplacements : le quai par défaut est créé tout seul.
    locs = client.get(f"/inventory/sites/{lyon['id']}/locations", headers=su).json()
    assert [(x["code"], x["is_default"]) for x in locs] == [("QUAI", True)]
    quai = locs[0]
    r = client.post(
        f"/inventory/sites/{lyon['id']}/locations",
        headers=su,
        json={"code": "a-01-2", "name": "Allée A"},
    )
    assert r.status_code == 201 and r.json()["code"] == "A-01-2"
    rack = r.json()
    r = client.post(f"/inventory/sites/{lyon['id']}/locations", headers=su, json={"code": "A-01-2"})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "code_existant")
    r = client.put(
        f"/inventory/locations/{quai['id']}", headers=su, json={"code": "QUAI", "is_default": False}
    )
    assert r.status_code == 422

    # --- Réception : 4 pneus à 60 € (remise 10 % sur 66,6667 → net 60) en deux DOT,
    # dont 1 en rayon ; 10 valves (pièce sans DOT).
    order = _order(
        client, su, supplier, lyon["id"], [(article, 8, "66.6667", 10), (valve, 10, "0.50", 0)]
    )
    l1, l2 = order["lines"]
    r = _receive(
        client,
        su,
        order,
        [
            {"line_id": l1["id"], "quantity": "3", "dot": "2324"},
            {"line_id": l1["id"], "quantity": "1", "dot": "0125", "location_id": rack["id"]},
            {"line_id": l2["id"], "quantity": "10"},
        ],
    )
    assert r.status_code == 200, r.text
    reception = r.json()["receptions"][0]
    assert {(x["dot"], x["location_id"]) for x in reception["lines"]} == {
        ("2324", quai["id"]),
        ("0125", rack["id"]),
        ("", quai["id"]),
    }
    # DOT invalide (semaine 54) refusé ; emplacement d'un autre dépôt refusé.
    bad = _receive(client, su, order, [{"line_id": l1["id"], "quantity": "1", "dot": "5424"}])
    assert bad.status_code == 422
    paris_quai = client.get(f"/inventory/sites/{paris['id']}/locations", headers=su).json()[0]
    bad = _receive(
        client, su, order, [{"line_id": l1["id"], "quantity": "1", "location_id": paris_quai["id"]}]
    )
    assert bad.status_code == 422 and "pas dans ce dépôt" in bad.json()["error"]["message"]

    stock = client.get(f"/inventory/articles/{article}", headers=su).json()
    assert D(stock["quantity"]) == 4 and D(stock["average_cost"]) == D("60.0000")
    assert D(stock["value"]) == D("240.00")
    assert [(x["location"]["code"], x["dot"], D(x["quantity"])) for x in stock["levels"]] == [
        ("A-01-2", "0125", 1),
        ("QUAI", "2324", 3),
    ]
    assert stock["moves"][0]["kind"] == "reception"
    assert stock["moves"][0]["reference"] == reception["number"]

    # --- Deuxième réception : 4 pneus à 70 € → CMP = (4×60 + 4×70) / 8 = 65.
    r = _receive(client, su, order, [{"line_id": l1["id"], "quantity": "0"}])
    assert r.status_code == 422
    order2 = _order(client, su, supplier, lyon["id"], [(article, 4, "70", 0)])
    r = _receive(
        client, su, order2, [{"line_id": order2["lines"][0]["id"], "quantity": "4", "dot": "5224"}]
    )
    assert r.status_code == 200, r.text
    stock = client.get(f"/inventory/articles/{article}", headers=su).json()
    assert D(stock["quantity"]) == 8 and D(stock["average_cost"]) == D("65.0000")

    # --- État du stock : tri par valeur, recherche, DOT le plus ancien (2324 = juin 2024).
    page = client.get("/inventory/stock", headers=su).json()
    assert page["total"] == 2 and D(page["total_value"]) == D("525.00")  # 8×65 + 10×0,50
    first = page["items"][0]
    assert first["article"]["id"] == article and first["oldest_dot"] == "2324"
    page = client.get("/inventory/stock?q=valve", headers=su).json()
    assert [x["article"]["id"] for x in page["items"]] == [valve]
    assert page["items"][0]["oldest_dot"] is None
    page = client.get(f"/inventory/stock?site_id={paris['id']}", headers=su).json()
    assert page["total"] == 0

    # --- Ajustements : sortie supérieure au stock refusée, casse acceptée au CMP.
    r = client.post(
        "/inventory/adjustments",
        headers=su,
        json={
            "article_id": article,
            "location_id": rack["id"],
            "dot": "0125",
            "quantity": "-2",
            "reason": "casse",
        },
    )
    assert (r.status_code, r.json()["error"]["code"]) == (409, "stock_insuffisant")
    r = client.post(
        "/inventory/adjustments",
        headers=su,
        json={
            "article_id": article,
            "location_id": rack["id"],
            "dot": "0125",
            "quantity": "-1",
            "reason": "casse",
            "note": "Flanc coupé",
        },
    )
    assert r.status_code == 201, r.text
    assert (r.json()["kind"], D(r.json()["unit_cost"])) == ("ajustement", D("65.0000"))
    r = client.post(
        "/inventory/adjustments",
        headers=su,
        json={"article_id": valve, "location_id": quai["id"], "quantity": "1", "reason": "hasard"},
    )
    assert r.status_code == 422  # motif inconnu

    # --- Transfert Lyon → Paris de 5 pneus, sans DOT précisé : les plus anciens partent.
    # Stock Lyon au quai : 2324×3 (juin 2024) et 5224×4 (déc. 2024) → 2324×3 puis 5224×2.
    r = client.post(
        "/inventory/transfers",
        headers=su,
        json={
            "from_site_id": lyon["id"],
            "to_site_id": paris["id"],
            "transferred_on": TODAY,
            "lines": [{"article_id": article, "from_location_id": quai["id"], "quantity": "5"}],
        },
    )
    assert r.status_code == 201, r.text
    transfer = r.json()
    assert transfer["number"].startswith(f"TR-{date.today().year}-")
    assert (transfer["line_count"], D(transfer["total_quantity"])) == (2, 5)
    entries = sorted(
        (m["dot"], D(m["quantity"])) for m in transfer["moves"] if D(m["quantity"]) > 0
    )
    assert entries == [("2324", 3), ("5224", 2)]
    stock = client.get(f"/inventory/articles/{article}", headers=su).json()
    assert D(stock["quantity"]) == 7 and D(stock["average_cost"]) == D("65.0000")  # CMP inchangé
    paris_levels = [x for x in stock["levels"] if x["site"]["id"] == paris["id"]]
    assert [(x["location"]["code"], x["dot"]) for x in paris_levels] == [
        ("QUAI", "2324"),
        ("QUAI", "5224"),
    ]
    # Trop demandé : rien n'est fait (tout ou rien).
    r = client.post(
        "/inventory/transfers",
        headers=su,
        json={
            "from_site_id": lyon["id"],
            "to_site_id": paris["id"],
            "transferred_on": TODAY,
            "lines": [
                {"article_id": valve, "from_location_id": quai["id"], "quantity": "2"},
                {"article_id": article, "from_location_id": quai["id"], "quantity": "50"},
            ],
        },
    )
    assert r.status_code == 409
    assert client.get("/inventory/transfers", headers=su).json()["total"] == 1
    valve_stock = client.get(f"/inventory/articles/{valve}", headers=su).json()
    assert D(valve_stock["quantity"]) == 10
    r = client.post(
        "/inventory/transfers",
        headers=su,
        json={
            "from_site_id": lyon["id"],
            "to_site_id": lyon["id"],
            "transferred_on": TODAY,
            "lines": [{"article_id": valve, "from_location_id": quai["id"], "quantity": "1"}],
        },
    )
    assert r.status_code == 422

    # --- Inventaire de Lyon : photo du stock théorique.
    r = client.post("/inventory/counts", headers=su, json={"site_id": lyon["id"]})
    assert r.status_code == 201, r.text
    count = r.json()
    assert count["number"].startswith("INV-") and count["status"] == "en_cours"
    expected = {
        (x["article"]["id"], x["location"]["code"], x["dot"]): D(x["expected_qty"])
        for x in count["lines"]
    }
    assert expected == {(article, "QUAI", "5224"): 2, (valve, "QUAI", ""): 10}
    r = client.post("/inventory/counts", headers=su, json={"site_id": lyon["id"]})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "inventaire_en_cours")

    # Pendant le comptage, une réception arrive (1 pneu DOT 2324 au quai) : elle doit rester.
    order3 = _order(client, su, supplier, lyon["id"], [(article, 1, "65", 0)])
    assert (
        _receive(
            client,
            su,
            order3,
            [{"line_id": order3["lines"][0]["id"], "quantity": "1", "dot": "2324"}],
        ).status_code
        == 200
    )

    tire_line = next(x for x in count["lines"] if x["article"]["id"] == article)
    count = client.put(
        f"/inventory/counts/{count['id']}/entries",
        headers=su,
        json={"entries": [{"line_id": tire_line["id"], "counted_qty": "1"}]},  # 1 manquant
    ).json()
    assert count["counted_count"] == 1 and D(count["value_difference"]) == D("-65.00")
    # Trouvé en rayon : 2 pneus DOT 0125 sur A-01-2 (non attendus, l'emplacement était vide).
    count = client.post(
        f"/inventory/counts/{count['id']}/lines",
        headers=su,
        json={"article_id": article, "location_id": rack["id"], "dot": "0125", "counted_qty": "2"},
    ).json()
    assert count["line_count"] == 3
    r = client.post(
        f"/inventory/counts/{count['id']}/validate", headers=su, json={"version": count["version"]}
    )
    assert r.status_code == 422 and "non comptée" in r.json()["error"]["message"]
    # Validation en comptant les valves non comptées à zéro.
    r = client.post(
        f"/inventory/counts/{count['id']}/validate",
        headers=su,
        json={"version": count["version"], "uncounted_as_zero": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "valide" and r.json()["validated_at"]
    stock = client.get(f"/inventory/articles/{article}", headers=su).json()
    lyon_levels = {
        (x["location"]["code"], x["dot"]): D(x["quantity"])
        for x in stock["levels"]
        if x["site"]["id"] == lyon["id"]
    }
    # QUAI 5224 : 2 théoriques, 1 compté → −1. La réception arrivée pendant le comptage
    # (QUAI 2324) est conservée : on applique l'écart, pas la quantité comptée.
    assert lyon_levels == {("QUAI", "5224"): 1, ("QUAI", "2324"): 1, ("A-01-2", "0125"): 2}
    valve_stock = client.get(f"/inventory/articles/{valve}", headers=su).json()
    assert D(valve_stock["quantity"]) == 0
    moves = client.get("/inventory/moves?kind=inventaire", headers=su).json()
    assert moves["total"] == 3 and {m["reference"] for m in moves["items"]} == {count["number"]}
    r = client.put(
        f"/inventory/counts/{count['id']}/entries",
        headers=su,
        json={"entries": [{"line_id": tire_line["id"], "counted_qty": "5"}]},
    )
    assert r.status_code == 409

    # Un inventaire annulé ne touche pas au stock.
    other = client.post("/inventory/counts", headers=su, json={"site_id": paris["id"]}).json()
    assert client.post(f"/inventory/counts/{other['id']}/cancel", headers=su).json()["status"] == (
        "annule"
    )
    assert client.get("/inventory/counts?status=valide", headers=su).json()["total"] == 1

    # --- Emplacement ayant eu du stock : suppression refusée.
    r = client.delete(f"/inventory/locations/{rack['id']}", headers=su)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "emplacement_utilise")

    # --- Journal inaltérable : le rôle applicatif ne peut ni modifier ni supprimer.
    with SessionLocal() as db:
        set_db_context(db, user_id=None, company_id=monde["a"])
        with pytest.raises(ProgrammingError):
            db.execute(text("UPDATE inventory.stock_moves SET quantity = 99"))
        db.rollback()
        set_db_context(db, user_id=None, company_id=monde["a"])
        with pytest.raises(ProgrammingError):
            db.execute(text("DELETE FROM inventory.stock_moves"))

    # --- Société B : rien de visible.
    in_b = {**su, "X-Company-Id": str(monde["b"])}
    assert client.get("/inventory/stock", headers=in_b).json()["total"] == 0
    assert client.get("/inventory/moves", headers=in_b).json()["total"] == 0


@pytest.mark.db
def test_droits_stock(client, monde):  # noqa: F811
    su = monde["su"]
    s = int(uid(), 16) % 10**8
    _, article, _ = _setup(client, su, s)
    site = _site(client, su, f"R{s % 10**6}")
    quai = client.get(f"/inventory/sites/{site['id']}/locations", headers=su).json()[0]
    client.post(
        "/inventory/adjustments",
        headers=su,
        json={
            "article_id": article,
            "location_id": quai["id"],
            "dot": "1025",
            "quantity": "4",
            "reason": "erreur",
            "unit_cost": "50",
        },
    )
    count = client.post("/inventory/counts", headers=su, json={"site_id": site["id"]}).json()

    user_id = monde["gestionnaire"]["id"]
    client.put(
        f"/auth/users/{user_id}/companies/{monde['a']}/permissions",
        headers=su,
        json={"permissions": ["inventory:read", "inventory:count"]},
    )
    counter = login(client, monde["gestionnaire"]["email"], monde["a"])
    assert client.get("/inventory/stock", headers=counter).status_code == 200
    adjust = {
        "article_id": article,
        "location_id": quai["id"],
        "dot": "1025",
        "quantity": "-1",
        "reason": "vol",
    }
    assert client.post("/inventory/adjustments", headers=counter, json=adjust).status_code == 403
    line = count["lines"][0]
    r = client.put(
        f"/inventory/counts/{count['id']}/entries",
        headers=counter,
        json={"entries": [{"line_id": line["id"], "counted_qty": "4"}]},
    )
    assert r.status_code == 200
    r = client.post(
        f"/inventory/counts/{count['id']}/validate",
        headers=counter,
        json={"version": r.json()["version"]},
    )
    assert r.status_code == 403
    # Un lecteur sans droit stock ne voit rien.
    lecteur = login(client, monde["lecteur"]["email"], monde["a"])
    assert client.get("/inventory/stock", headers=lecteur).status_code == 403
