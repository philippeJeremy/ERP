"""Tests du catalogue : articles, fournisseurs des articles, imports de tarifs."""

import io
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.catalog.files import read_table, suggest_mapping
from app.modules.catalog.tires import gtin_is_valid, parse_designation, search_digits
from tests.test_admin_utilisateurs import login, monde, uid  # noqa: F401  (fixture)

# --- Tests unitaires (sans base) ------------------------------------------------------


def test_lecture_designation_pneu():
    d = parse_designation("MICHELIN 205/55 R16 91V XL PRIMACY 4")
    assert (d["width"], d["aspect_ratio"], d["rim"]) == (Decimal(205), 55, Decimal(16))
    assert (d["load_index"], d["speed_index"], d["reinforced"]) == ("91", "V", True)
    pl = parse_designation("315/80 R22.5 156/150L X MULTI D")
    assert (pl["vehicle_type"], pl["load_index"]) == ("poids_lourd", "156/150")
    assert parse_designation("195/70 R15C 104/102R")["vehicle_type"] == "utilitaire"
    hiver = parse_designation("225/45R17 94V XL M+S 3PMSF ALPIN 6")
    assert hiver["season"] == "hiver" and hiver["three_pmsf"] and hiver["mud_snow"]
    assert parse_designation("225/50 R17 94W RFT")["runflat"]
    assert parse_designation("Valve TR414") == {}


def test_ean_et_recherche_dimension():
    assert gtin_is_valid("4006381333931")
    assert not gtin_is_valid("4006381333932")
    assert search_digits("205/55 R16") == "2055516"
    assert search_digits("205 55 16") == "2055516"
    assert search_digits("primacy") is None


def test_lecture_csv_windows_et_proposition_colonnes():
    content = "Réf;EAN;Marque;Désignation;Prix net HT;PVC\nA1;4006381333931;X;Y;1,5;3\n"
    table = read_table(content.encode("cp1252"), "tarif.csv")
    assert table.detected["delimiter"] == ";" and table.detected["encoding"] == "cp1252"
    mapping = suggest_mapping(table.headers)
    assert mapping["purchase_price"] == "Prix net HT"  # pas le prix public conseillé
    assert mapping["supplier_ref"] == "Réf" and mapping["ean"] == "EAN"


# --- Tests avec base ------------------------------------------------------------------

pytestmark_db = pytest.mark.db


def ean(seed: int) -> str:
    """EAN-13 valide (préfixe 200 : usage interne, jamais attribué à un vrai produit)."""
    body = f"200{seed % 10**9:09d}"
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return body + str((10 - total % 10) % 10)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _seed() -> int:
    return int(uid(), 16) % 10**8


@pytest.mark.db
def test_article_pneu_et_fournisseurs(client, monde):  # noqa: F811
    su = monde["su"]
    s = _seed()
    r = client.post(
        "/catalog/articles",
        headers=su,
        json={
            "kind": "pneu",
            "ean": ean(s),
            "brand": "michelin",
            "tire": {"width": "205", "aspect_ratio": 55, "rim": "16", "load_index": "91",
                     "speed_index": "V", "season": "ete", "reinforced": True,
                     "fuel_class": "B", "wet_class": "A", "noise_db": 69},
        },
    )  # fmt: skip
    assert r.status_code == 201, r.text
    article = r.json()
    assert article["code"].startswith("A")
    assert article["designation"] == "MICHELIN 205/55 R16 91V XL"  # construite automatiquement
    assert article["tire"]["size"] == "205/55 R16 91V"
    assert article["tire"]["size_code"] == "2055516"
    # Même EAN → 409 ; EAN faux → 422 ; même marque en majuscules → même marque.
    r = client.post("/catalog/articles", headers=su, json={"kind": "pneu", "ean": ean(s)})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "ean_existant")
    assert (
        client.post(
            "/catalog/articles",
            headers=su,
            json={"kind": "piece", "designation": "X", "ean": "123"},
        ).status_code
        == 422
    )
    valve = {"kind": "accessoire", "designation": "Valve", "brand": "MICHELIN"}
    r = client.post("/catalog/articles", headers=su, json=valve)
    assert r.json()["brand"]["id"] == article["brand"]["id"]

    # Recherche par dimension, sous plusieurs écritures.
    for q in ("205/55R16", "205 55 16", "2055516"):
        page = client.get(f"/catalog/articles?q={q}&kind=pneu", headers=su).json()
        assert article["id"] in [i["id"] for i in page["items"]], q

    # Deux fournisseurs : nombre et meilleur prix dans la liste ; un seul préféré.
    f1 = client.post("/partners", headers=su, json={"name": f"F1 {s}"}).json()["id"]
    f2 = client.post("/partners", headers=su, json={"name": f"F2 {s}"}).json()["id"]
    url = f"/catalog/articles/{article['id']}/suppliers"
    offer = {"partner_id": f1, "purchase_price": "62.5", "supplier_ref": "MI-1"}
    l1 = client.post(url, headers=su, json={**offer, "is_preferred": True})
    assert l1.status_code == 201, l1.text
    offer = {"partner_id": f2, "purchase_price": "59.9", "is_preferred": True}
    l2 = client.post(url, headers=su, json=offer)
    assert client.post(url, headers=su, json={"partner_id": f2}).status_code == 409
    links = client.get(url, headers=su).json()
    assert [x["is_preferred"] for x in links if x["id"] == l1.json()["id"]] == [False]
    item = next(i for i in client.get(f"/catalog/articles?q={ean(s)}", headers=su).json()["items"])
    assert (item["supplier_count"], Decimal(item["best_price"])) == (2, Decimal("59.9"))
    # Un article avec des fournisseurs ne se supprime pas.
    r = client.delete(f"/catalog/articles/{article['id']}", headers=su)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "article_utilise")

    # Société B : l'article (commun) est visible, mais pas les fournisseurs ni les prix de A.
    in_b = {**su, "X-Company-Id": str(monde["b"])}
    assert client.get(f"/catalog/articles/{article['id']}", headers=in_b).status_code == 200
    assert client.get(url, headers=in_b).json() == []
    assert client.post(url, headers=in_b, json={"partner_id": f1}).status_code == 404
    assert l2.status_code == 201


def _csv(rows: list[list[str]]) -> bytes:
    lines = ["Réf fournisseur;EAN;Marque;Désignation;Prix net HT"]
    lines += [";".join(r) for r in rows]
    return "\n".join(lines).encode("cp1252")


def _upload(client, headers, profile_id, content, name="tarif.csv"):
    r = client.post(
        "/catalog/imports",
        headers=headers,
        data={"profile_id": str(profile_id)},
        files={"file": (name, content, "text/csv")},
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.db
def test_import_tarif_complet(client, monde):  # noqa: F811
    su = monde["su"]
    s = _seed()
    supplier = client.post("/partners", headers=su, json={"name": f"Grossiste {s}"}).json()["id"]
    rows = [
        [f"R{s}-1", ean(s + 1), "Michelin", "205/55 R16 91V PRIMACY 4", "65,40"],
        [f"R{s}-2", ean(s + 2), "Continental", "225/45R17 94V XL WinterContact 3PMSF", "88.10"],
        [f"R{s}-3", "", "Bosch", "Valve TR414", "0,35"],
        [f"R{s}-4", "123", "X", "EAN faux", "10"],
        [f"R{s}-5", ean(s + 5), "Pirelli", "", "abc"],
        [f"R{s}-1", ean(s + 1), "Michelin", "doublon", "1"],
    ]

    # Aperçu : colonnes proposées automatiquement.
    r = client.post(
        "/catalog/imports/preview",
        headers=su,
        files={"file": ("tarif.csv", _csv(rows), "text/csv")},
    )
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["delimiter"] == ";" and len(preview["rows"]) == 6
    mapping = preview["suggested_mapping"]
    assert mapping["purchase_price"] == "Prix net HT" and mapping["ean"] == "EAN"

    r = client.post(
        "/catalog/import-profiles",
        headers=su,
        json={"partner_id": supplier, "name": "Tarif", "file_format": "csv", "delimiter": ";",
              "mapping": mapping, "full_catalog": True, "default_kind": "pneu"},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    profile = r.json()["id"]

    # Analyse (exécutée tout de suite en test) : rien n'est encore écrit.
    run = _upload(client, su, profile, _csv(rows))
    run = client.get(f"/catalog/imports/{run['id']}", headers=su).json()
    assert run["status"] == "pret", run
    assert (run["new_count"], run["error_count"], run["total_lines"]) == (3, 3, 6)
    errors = client.get(f"/catalog/imports/{run['id']}/lines?status=erreur", headers=su).json()
    messages = " | ".join(e["error"] for e in errors["items"])
    assert "invalide" in messages and "illisible" in messages and "Doublon" in messages
    assert client.get(f"/catalog/articles?q=R{s}-1", headers=su).json()["total"] == 0

    # Application.
    r = client.post(f"/catalog/imports/{run['id']}/apply", headers=su, json={})
    assert r.status_code == 200, r.text
    run = client.get(f"/catalog/imports/{run['id']}", headers=su).json()
    assert run["status"] == "termine", run
    links = client.get(f"/catalog/article-suppliers?partner_id={supplier}", headers=su).json()
    assert links["total"] == 3
    winter = client.get(f"/catalog/articles?q={ean(s + 2)}", headers=su).json()["items"][0]
    assert (winter["size"], winter["season"]) == ("225/45 R17 94V", "hiver")
    valve = next(x for x in links["items"] if x["supplier_ref"] == f"R{s}-3")
    assert valve["article"]["ean"] is None
    # La valve a été créée comme « pneu » (type par défaut du profil) : sans dimension.

    # 2e tarif : un prix change, un article disparaît (arrêté), un nouveau arrive.
    rows2 = [
        [f"R{s}-1", ean(s + 1), "Michelin", "205/55 R16 91V PRIMACY 4", "66,00"],
        [f"R{s}-3", "", "Bosch", "Valve TR414", "0,35"],
        [f"R{s}-6", ean(s + 6), "Michelin", "195/65 R15 91H", "50"],
    ]
    run2 = _upload(client, su, profile, _csv(rows2))
    run2 = client.get(f"/catalog/imports/{run2['id']}", headers=su).json()
    assert (run2["updated_count"], run2["unchanged_count"], run2["new_count"],
            run2["discontinued_count"]) == (1, 1, 1, 1)  # fmt: skip
    maj = client.get(f"/catalog/imports/{run2['id']}/lines?status=maj", headers=su).json()
    assert (Decimal(maj["items"][0]["old_price"]), Decimal(maj["items"][0]["new_price"])) == (
        Decimal("65.4"),
        Decimal("66"),
    )
    client.post(f"/catalog/imports/{run2['id']}/apply", headers=su, json={})
    stopped = client.get(
        f"/catalog/article-suppliers?partner_id={supplier}&discontinued=true", headers=su
    ).json()
    assert [x["article"]["ean"] for x in stopped["items"]] == [ean(s + 2)]

    # 3e tarif : le revoilà → réactivé.
    run3 = _upload(client, su, profile, _csv(rows2 + [rows[1]]))
    run3 = client.get(f"/catalog/imports/{run3['id']}", headers=su).json()
    assert run3["reactivated_count"] == 1
    client.post(f"/catalog/imports/{run3['id']}/cancel", headers=su)
    assert client.get(f"/catalog/imports/{run3['id']}", headers=su).json()["status"] == "annule"


@pytest.mark.db
def test_import_garde_fou_et_excel(client, monde):  # noqa: F811
    from openpyxl import Workbook

    su = monde["su"]
    s = _seed()
    supplier = client.post("/partners", headers=su, json={"name": f"Excel {s}"}).json()["id"]

    def xlsx(rows):
        book = Workbook()
        ws = book.active
        ws.title = "Tarif"
        ws.append(["Titre du fichier"])  # une ligne avant les titres
        ws.append(["Code", "EAN", "Libellé", "Prix"])
        for row in rows:
            ws.append(row)
        buffer = io.BytesIO()
        book.save(buffer)
        return buffer.getvalue()

    # EAN lu par Excel comme un nombre (int) : doit rester un EAN valide.
    rows = [
        [f"X{i}", int(ean((s % 10**6) * 100 + i)), f"185/65 R15 88T n°{i}", 40 + i]
        for i in range(20)
    ]
    content = xlsx(rows)
    preview = client.post(
        "/catalog/imports/preview",
        headers=su,
        data={"header_row": "2"},
        files={"file": ("tarif.xlsx", content, "application/octet-stream")},
    ).json()
    assert preview["sheets"] == ["Tarif"] and preview["headers"][:2] == ["Code", "EAN"]
    profile = client.post(
        "/catalog/import-profiles",
        headers=su,
        json={"partner_id": supplier, "file_format": "excel", "header_row": 2,
              "mapping": preview["suggested_mapping"], "default_vehicle_type": "tourisme"},
    ).json()["id"]  # fmt: skip
    run = _upload(client, su, profile, content, "tarif.xlsx")
    assert client.get(f"/catalog/imports/{run['id']}", headers=su).json()["new_count"] == 20
    client.post(f"/catalog/imports/{run['id']}/apply", headers=su, json={})

    # Fichier tronqué : 5 lignes sur 20 → 15 arrêts : confirmation obligatoire.
    run = _upload(client, su, profile, xlsx(rows[:5]), "tarif.xlsx")
    run = client.get(f"/catalog/imports/{run['id']}", headers=su).json()
    assert run["discontinued_count"] == 15 and run["needs_confirmation"]
    r = client.post(f"/catalog/imports/{run['id']}/apply", headers=su, json={})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "confirmation_requise")
    r = client.post(
        f"/catalog/imports/{run['id']}/apply", headers=su, json={"confirm_discontinue": True}
    )
    assert r.status_code == 200
    assert client.get(f"/catalog/imports/{run['id']}", headers=su).json()["status"] == "termine"

    # Le format du fournisseur change : colonne disparue → erreur claire.
    book = Workbook()
    book.active.append(["x"])
    book.active.append(["Code", "Libellé", "Prix"])
    buffer = io.BytesIO()
    book.save(buffer)
    run = _upload(client, su, profile, buffer.getvalue(), "tarif.xlsx")
    run = client.get(f"/catalog/imports/{run['id']}", headers=su).json()
    assert run["status"] == "erreur" and "EAN" in run["message"]

    # Droits : sans catalog:import → 403.
    lecteur = login(client, monde["lecteur"]["email"], monde["a"])
    assert client.get("/catalog/imports", headers=lecteur).status_code == 403
