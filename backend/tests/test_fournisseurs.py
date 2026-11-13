"""Tests du module tiers : fiches fournisseurs, adresses, contacts, validations, isolation."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.partners.schemas import iban_is_valid
from tests.test_admin_utilisateurs import login, monde, uid  # noqa: F401  (fixture)

IBAN_OK = "FR76 3000 6000 0112 3456 7890 189"


def test_cle_iban():
    assert iban_is_valid(IBAN_OK.replace(" ", ""))
    assert not iban_is_valid("FR7630006000011234567890188")  # un chiffre changé
    assert not iban_is_valid("XX00")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _siret() -> str:
    return str(int(uid(), 16) % 10**14).zfill(14)


@pytest.mark.db
def test_fiche_fournisseur_complete(client, monde):  # noqa: F811
    su = monde["su"]
    siret = _siret()
    r = client.post(
        "/partners",
        headers=su,
        json={
            "name": "Michelin Distribution",
            "siret": f"{siret[:3]} {siret[3:6]} {siret[6:9]} {siret[9:]}",
            "iban": IBAN_OK,
            "bic": "bnpafrpp",
            "payment_method": "virement",
            "payment_days": 45,
            "payment_end_of_month": True,
            "free_shipping_amount": "1500.00",
        },
    )
    assert r.status_code == 201, r.text
    fiche = r.json()
    # Code automatique, SIRET/IBAN/BIC nettoyés (espaces retirés, majuscules).
    assert fiche["code"].startswith("T") and len(fiche["code"]) == 6
    assert (fiche["siret"], fiche["iban"], fiche["bic"]) == (
        siret,
        IBAN_OK.replace(" ", ""),
        "BNPAFRPP",
    )
    assert fiche["is_supplier"] and not fiche["is_customer"]
    pid = fiche["id"]

    # Le code suivant est consécutif.
    r2 = client.post("/partners", headers=su, json={"name": "Second"})
    assert int(r2.json()["code"][1:]) == int(fiche["code"][1:]) + 1

    # Doublons : même SIRET, même code → 409.
    r = client.post("/partners", headers=su, json={"name": "Copie", "siret": siret})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "siret_existant")
    r = client.post("/partners", headers=su, json={"name": "Copie", "code": fiche["code"]})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "code_existant")

    # Validations : IBAN faux, SIRET trop court, aucun rôle.
    assert (
        client.post(
            "/partners", headers=su, json={"name": "X", "iban": "FR7630006000011234567890188"}
        ).status_code
        == 422
    )
    assert (
        client.post("/partners", headers=su, json={"name": "X", "siret": "123"}).status_code == 422
    )
    assert (
        client.post("/partners", headers=su, json={"name": "X", "is_supplier": False}).status_code
        == 422
    )

    # Adresses : la première d'un type est principale ; en cocher une autre décoche l'ancienne.
    base = {"line1": "1 rue A", "postal_code": "63000", "city": "Clermont-Ferrand"}
    a1 = client.post(f"/partners/{pid}/addresses", headers=su, json={**base, "kind": "siege"})
    assert a1.status_code == 201 and a1.json()["is_primary"]
    c1 = client.post(f"/partners/{pid}/addresses", headers=su, json={**base, "kind": "commande"})
    c2 = client.post(
        f"/partners/{pid}/addresses",
        headers=su,
        json={**base, "kind": "commande", "city": "Lyon", "is_primary": True},
    )
    assert c2.json()["is_primary"]
    fiche = client.get(f"/partners/{pid}", headers=su).json()
    primaires = {a["id"]: a["is_primary"] for a in fiche["addresses"]}
    assert primaires[c1.json()["id"]] is False and primaires[c2.json()["id"]] is True
    # Supprimer la principale : l'autre du même type reprend le rôle.
    client.delete(f"/partners/{pid}/addresses/{c2.json()['id']}", headers=su)
    fiche = client.get(f"/partners/{pid}", headers=su).json()
    assert [a["is_primary"] for a in fiche["addresses"] if a["kind"] == "commande"] == [True]

    # Contacts.
    r = client.post(
        f"/partners/{pid}/contacts",
        headers=su,
        json={"first_name": "Anne", "last_name": "Durand", "email": "anne@exemple.fr"},
    )
    assert r.status_code == 201 and r.json()["is_primary"]
    r = client.post(f"/partners/{pid}/contacts", headers=su, json={"last_name": "Martin"})
    assert not r.json()["is_primary"]

    # Liste : recherche par nom de contact, ville du siège, interlocuteur principal.
    page = client.get("/partners?role=supplier&q=durand", headers=su).json()
    assert page["total"] == 1
    item = page["items"][0]
    assert (item["city"], item["contact_name"]) == ("Clermont-Ferrand", "Anne Durand")
    assert client.get("/partners?role=customer", headers=su).json()["total"] == 0

    # Modification avec verrouillage optimiste.
    r = client.patch(
        f"/partners/{pid}",
        headers=su,
        json={"version": fiche["version"], "lead_time_days": 3, "is_customer": True},
    )
    assert r.status_code == 200 and r.json()["is_customer"]
    r = client.patch(
        f"/partners/{pid}", headers=su, json={"version": fiche["version"], "notes": "x"}
    )
    assert (r.status_code, r.json()["error"]["code"]) == (409, "modifie_entre_temps")

    # Groupement : pas de boucle.
    second = r2.json()
    v = client.get(f"/partners/{pid}", headers=su).json()["version"]
    assert (
        client.patch(
            f"/partners/{pid}", headers=su, json={"version": v, "parent_id": second["id"]}
        ).status_code
        == 200
    )
    r = client.patch(
        f"/partners/{second['id']}",
        headers=su,
        json={"version": second["version"], "parent_id": pid},
    )
    assert r.status_code == 422

    # Suppression : la fiche, ses adresses et contacts disparaissent.
    assert client.delete(f"/partners/{pid}", headers=su).status_code == 204
    assert client.get(f"/partners/{pid}", headers=su).status_code == 404


@pytest.mark.db
def test_isolation_et_droits(client, monde):  # noqa: F811
    su = monde["su"]
    siret = _siret()
    pid = client.post("/partners", headers=su, json={"name": "Fourn A", "siret": siret}).json()[
        "id"
    ]

    # Dans la société B : la fiche de A est invisible, et le même SIRET est permis.
    in_b = {**su, "X-Company-Id": str(monde["b"])}
    assert client.get(f"/partners/{pid}", headers=in_b).status_code == 404
    assert client.get("/partners", headers=in_b).json()["total"] == 0
    r = client.post("/partners", headers=in_b, json={"name": "Fourn B", "siret": siret})
    assert r.status_code == 201
    assert (
        client.patch(
            f"/partners/{r.json()['id']}",
            headers=in_b,
            json={"version": 1, "parent_id": pid},  # groupement d'une autre société
        ).status_code
        == 422
    )

    # Sans partners:read → 403 ; avec partners:read seul → lecture, pas d'écriture.
    lecteur = login(client, monde["lecteur"]["email"], monde["a"])
    assert client.get("/partners", headers=lecteur).status_code == 403
    # Droit individuel (v0.6) donné au gestionnaire, sans créer de rôle.
    email = monde["gestionnaire"]["email"]
    r = client.put(
        f"/auth/users/{monde['gestionnaire']['id']}/companies/{monde['a']}/permissions",
        headers=su,
        json={"permissions": ["partners:read"]},
    )
    assert r.status_code == 200, r.text
    user = login(client, email, monde["a"])
    assert client.get(f"/partners/{pid}", headers=user).status_code == 200
    assert client.post("/partners", headers=user, json={"name": "Non"}).status_code == 403
    assert client.delete(f"/partners/{pid}", headers=user).status_code == 403
