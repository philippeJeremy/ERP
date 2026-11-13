"""Tests de la gestion des sociétés : création, modification, désactivation, suppression."""

import random

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.test_admin_utilisateurs import login, monde, uid  # noqa: F401  (fixture)
from tests.test_multisociete import owner_conn

pytestmark = pytest.mark.db


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_creation_et_modification(client, monde):  # noqa: F811
    su = monde["su"]
    code = f"N{uid().upper()}"
    siren = f"{random.randrange(10**9):09d}"
    r = client.post(
        "/org/companies",
        headers=su,
        json={"code": code, "name": "Nouvelle filiale", "siren": siren, "city": "Lyon"},
    )
    assert r.status_code == 201, r.text
    company = r.json()
    r = client.post(
        "/org/companies",
        headers=su,
        json={"code": f"S{uid().upper()}", "name": "Même SIREN", "siren": siren},
    )
    assert (r.status_code, r.json()["error"]["code"]) == (409, "siren_existant")
    in_new = {**su, "X-Company-Id": str(company["id"])}
    assert len(client.get("/org/sequences", headers=in_new).json()) == 6
    assert (
        client.post(
            "/org/companies", headers=su, json={"code": code, "name": "Doublon"}
        ).status_code
        == 409
    )

    r = client.patch(
        f"/org/companies/{company['id']}",
        headers=in_new,
        json={"version": company["version"], "name": "Filiale Sud", "siren": None, "city": "Nice"},
    )
    assert r.status_code == 200
    assert (r.json()["name"], r.json()["siren"], r.json()["city"]) == ("Filiale Sud", None, "Nice")

    # Un administrateur de A modifie A, mais ni B, ni la création, ni l'activation.
    admin = login(client, monde["admin"]["email"], monde["a"])
    a = client.get(f"/org/companies/{monde['a']}", headers=admin).json()
    assert (
        client.patch(
            f"/org/companies/{monde['a']}",
            headers=admin,
            json={"version": a["version"], "city": "Paris"},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/org/companies/{monde['b']}", headers=admin, json={"version": 1, "city": "Paris"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/org/companies", headers=admin, json={"code": f"X{uid().upper()}", "name": "X"}
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/org/companies/{monde['a']}",
            headers=admin,
            json={"version": a["version"] + 1, "is_active": False},
        ).status_code
        == 403
    )
    assert client.delete(f"/org/companies/{monde['a']}", headers=admin).status_code == 403


def test_societe_desactivee(client, monde):  # noqa: F811
    su = monde["su"]
    admin = login(client, monde["admin"]["email"], monde["a"])
    a = client.get(f"/org/companies/{monde['a']}", headers=su).json()
    assert (
        client.patch(
            f"/org/companies/{monde['a']}",
            headers=su,
            json={"version": a["version"], "is_active": False},
        ).status_code
        == 200
    )

    # Les utilisateurs n'y ont plus accès et ne la voient plus dans leur liste…
    r = client.get("/auth/users", headers=admin)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "societe_desactivee")
    no_company = {k: v for k, v in admin.items() if k != "X-Company-Id"}
    assert client.get("/org/companies", headers=no_company).json() == []
    # … mais le super-administrateur la voit toujours et peut la réactiver.
    assert monde["a"] in [c["id"] for c in client.get("/org/companies", headers=su).json()]
    a = client.get(f"/org/companies/{monde['a']}", headers=su).json()
    client.patch(
        f"/org/companies/{monde['a']}",
        headers=su,
        json={"version": a["version"], "is_active": True},
    )
    assert client.get("/auth/users", headers=admin).status_code == 200


def test_suppression(client, monde):  # noqa: F811
    su = monde["su"]
    admin = login(client, monde["admin"]["email"], monde["a"])
    assert client.delete(f"/org/companies/{monde['a']}", headers=su).status_code == 204
    assert client.get(f"/org/companies/{monde['a']}", headers=su).status_code == 404
    # Compteurs et rôles de la société supprimés avec elle ; les comptes, eux, restent.
    with owner_conn() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM org.number_sequences WHERE company_id = %s", (monde["a"],)
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM auth.user_company_roles WHERE company_id = %s", (monde["a"],)
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM auth.users WHERE id = %s", (monde["admin"]["id"],)
            ).fetchone()[0]
            == 1
        )
        # La suppression est tracée dans le journal d'audit.
        assert (
            conn.execute(
                "SELECT count(*) FROM audit.audit_log WHERE table_name = 'companies' "
                "AND action = 'DELETE' AND record_id = %s",
                (str(monde["a"]),),
            ).fetchone()[0]
            == 1
        )
    assert client.get("/auth/users", headers=admin).status_code == 403
    assert client.delete(f"/org/companies/{monde['a']}", headers=su).status_code == 404
