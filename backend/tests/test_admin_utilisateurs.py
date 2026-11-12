"""Tests de l'administration : comptes, rôles, et règles anti-escalade de privilèges."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.context import RequestContext
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.main import app
from app.modules.auth.models import User
from app.modules.org import service as org_service
from app.modules.org.schemas import CompanyCreate
from tests.test_multisociete import owner_conn

pytestmark = pytest.mark.db
PASSWORD = "mot-de-passe-de-test-123"


def uid() -> str:
    return uuid.uuid4().hex[:8]


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def login(client: TestClient, email: str, company: int | None = None, password: str = PASSWORD):
    r = client.post("/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    if company is not None:
        headers["X-Company-Id"] = str(company)
    return headers


@pytest.fixture
def monde(client):
    """Un super-admin, deux sociétés, et dans A : un admin, un gestionnaire, un lecteur."""
    with SessionLocal() as db:
        root = User(
            email=f"root-{uid()}@test.fr",
            full_name="Root",
            password_hash=hash_password(PASSWORD),
            is_superuser=True,
        )
        db.add(root)
        db.commit()
        ctx = RequestContext(user_id=root.id, is_superuser=True)
        a = org_service.create_company(
            db, ctx, CompanyCreate(code=f"A{uid().upper()}", name="A")
        ).id
        b = org_service.create_company(
            db, ctx, CompanyCreate(code=f"B{uid().upper()}", name="B")
        ).id
        root_email = root.email
    su = login(client, root_email, a)
    roles = {r["code"]: r["id"] for r in client.get("/auth/roles", headers=su).json()}

    def role(prefix: str, permissions: list[str]) -> int:
        r = client.post(
            "/auth/roles",
            headers=su,
            json={
                "code": f"{prefix}_{uid()}",
                "name": prefix.capitalize(),
                "permissions": permissions,
            },
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def user(prefix: str, role_ids: list[int]) -> dict:
        email = f"{prefix}-{uid()}@test.fr"
        r = client.post(
            "/auth/users",
            headers=su,
            json={
                "email": email,
                "full_name": prefix.capitalize(),
                "password": PASSWORD,
                "role_ids": role_ids,
            },
        )
        assert r.status_code == 201, r.text
        # Ces comptes de test ont « déjà changé » leur mot de passe provisoire.
        with owner_conn() as conn:
            conn.execute(
                "UPDATE auth.users SET must_change_password = false WHERE email = %s", (email,)
            )
        return {"id": r.json()["id"], "email": email}

    gestionnaire_role = role("gestionnaire", ["auth:read", "auth:manage"])
    lecteur_role = role("lecteur", ["org:read"])
    return {
        "a": a,
        "b": b,
        "su": su,
        "root_email": root_email,
        "admin_role": roles["admin"],
        "gestionnaire_role": gestionnaire_role,
        "lecteur_role": lecteur_role,
        "admin": user("admin", [roles["admin"]]),
        "gestionnaire": user("gestionnaire", [gestionnaire_role]),
        "lecteur": user("lecteur", [lecteur_role]),
    }


def test_creation_et_liste(client, monde):
    h = login(client, monde["admin"]["email"], monde["a"])
    r = client.post(
        "/auth/users",
        headers=h,
        json={
            "email": f"nouveau-{uid()}@test.fr",
            "full_name": "Nouveau",
            "password": PASSWORD,
            "role_ids": [monde["lecteur_role"]],
        },
    )
    assert r.status_code == 201
    assert [x["id"] for x in r.json()["roles"]] == [monde["lecteur_role"]]
    assert r.json()["id"] in [u["id"] for u in client.get("/auth/users", headers=h).json()]

    # Sans rôle : refusé. E-mail déjà pris : conflit identifiable par le frontend.
    r = client.post(
        "/auth/users",
        headers=h,
        json={
            "email": f"x-{uid()}@test.fr",
            "full_name": "X",
            "password": PASSWORD,
            "role_ids": [],
        },
    )
    assert r.json()["error"]["code"] == "role_requis"
    r = client.post(
        "/auth/users",
        headers=h,
        json={
            "email": monde["lecteur"]["email"].upper(),
            "full_name": "X",
            "password": PASSWORD,
            "role_ids": [monde["lecteur_role"]],
        },
    )
    assert (r.status_code, r.json()["error"]["code"]) == (409, "compte_existant")


def test_modification_et_desactivation(client, monde):
    h = login(client, monde["admin"]["email"], monde["a"])
    lecteur = monde["lecteur"]
    session = client.post("/auth/login", data={"username": lecteur["email"], "password": PASSWORD})
    cookie = next(c for c in session.headers.get_list("set-cookie")).split(";")[0]

    new_email = f"renomme-{uid()}@test.fr"
    r = client.patch(
        f"/auth/users/{lecteur['id']}", headers=h, json={"full_name": "Renommé", "email": new_email}
    )
    assert r.status_code == 200 and r.json()["full_name"] == "Renommé"
    login(client, new_email)

    r = client.patch(f"/auth/users/{lecteur['id']}", headers=h, json={"is_active": False})
    assert r.json()["is_active"] is False
    # Le compte ne peut plus se connecter, et sa session ouverte est fermée.
    assert (
        client.post("/auth/login", data={"username": new_email, "password": PASSWORD}).status_code
        == 401
    )
    assert client.post("/auth/refresh", headers={"Cookie": cookie}).status_code == 401

    # On ne se désactive pas soi-même.
    r = client.patch(f"/auth/users/{monde['admin']['id']}", headers=h, json={"is_active": False})
    assert r.status_code == 400


def test_reinitialisation_du_mot_de_passe(client, monde):
    h = login(client, monde["admin"]["email"], monde["a"])
    lecteur = monde["lecteur"]
    r = client.post(
        f"/auth/users/{lecteur['id']}/password",
        headers=h,
        json={"new_password": "un-tout-nouveau-mdp-789"},
    )
    assert r.status_code == 204
    assert (
        client.post(
            "/auth/login", data={"username": lecteur["email"], "password": PASSWORD}
        ).status_code
        == 401
    )
    login(client, lecteur["email"], password="un-tout-nouveau-mdp-789")
    # Pour soi-même : passer par le profil (qui demande le mot de passe actuel).
    r = client.post(
        f"/auth/users/{monde['admin']['id']}/password",
        headers=h,
        json={"new_password": "un-tout-nouveau-mdp-789"},
    )
    assert r.status_code == 400


def test_roles_d_un_utilisateur(client, monde):
    h = login(client, monde["admin"]["email"], monde["a"])
    lecteur = monde["lecteur"]
    url = f"/auth/users/{lecteur['id']}/roles"
    r = client.put(
        url, headers=h, json={"role_ids": [monde["lecteur_role"], monde["gestionnaire_role"]]}
    )
    assert {x["id"] for x in r.json()["roles"]} == {
        monde["lecteur_role"],
        monde["gestionnaire_role"],
    }
    r = client.put(url, headers=h, json={"role_ids": [monde["gestionnaire_role"]]})
    assert [x["id"] for x in r.json()["roles"]] == [monde["gestionnaire_role"]]

    # Liste vide : l'accès à la société est retiré.
    assert client.put(url, headers=h, json={"role_ids": []}).status_code == 200
    assert lecteur["id"] not in [u["id"] for u in client.get("/auth/users", headers=h).json()]
    assert (
        client.get("/auth/users", headers=login(client, lecteur["email"], monde["a"])).status_code
        == 403
    )

    # Personne ne modifie ses propres rôles.
    r = client.put(f"/auth/users/{monde['admin']['id']}/roles", headers=h, json={"role_ids": []})
    assert r.status_code == 400


def test_pas_d_escalade_de_privileges(client, monde):
    """Un gestionnaire (auth:manage, sans les autres droits) ne peut pas devenir admin."""
    h = login(client, monde["gestionnaire"]["email"], monde["a"])
    admin, lecteur = monde["admin"], monde["lecteur"]

    # Ni attribuer un rôle qui donne des droits qu'il n'a pas (admin, ou même « lecteur »
    # = org:read, qu'il ne possède pas)…
    r = client.put(
        f"/auth/users/{lecteur['id']}/roles",
        headers=h,
        json={"role_ids": [monde["lecteur_role"], monde["admin_role"]]},
    )
    assert r.status_code == 403, r.text
    for role_id in (monde["admin_role"], monde["lecteur_role"]):
        r = client.post(
            "/auth/users",
            headers=h,
            json={
                "email": f"complice-{uid()}@test.fr",
                "full_name": "Complice",
                "password": PASSWORD,
                "role_ids": [role_id],
            },
        )
        assert r.status_code == 403, r.text
    # … ni retirer son rôle à l'admin, ni prendre la main sur son compte.
    assert (
        client.put(f"/auth/users/{admin['id']}/roles", headers=h, json={"role_ids": []}).status_code
        == 403
    )
    assert (
        client.post(
            f"/auth/users/{admin['id']}/password",
            headers=h,
            json={"new_password": "je-prends-le-controle-1"},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/auth/users/{admin['id']}", headers=h, json={"email": f"pirate-{uid()}@test.fr"}
        ).status_code
        == 403
    )
    assert (
        client.patch(f"/auth/users/{admin['id']}", headers=h, json={"is_active": False}).status_code
        == 403
    )
    # En revanche il gère les comptes de son niveau.
    r = client.post(
        "/auth/users",
        headers=h,
        json={
            "email": f"collegue-{uid()}@test.fr",
            "full_name": "Collègue",
            "password": PASSWORD,
            "role_ids": [monde["gestionnaire_role"]],
        },
    )
    assert r.status_code == 201
    # Sans auth:manage : rien du tout.
    lecteur_h = login(client, lecteur["email"], monde["a"])
    assert client.get("/auth/users", headers=lecteur_h).status_code == 403


def test_compte_partage_entre_societes(client, monde):
    """L'admin de A ne peut pas prendre la main sur un compte qui a aussi accès à B."""
    su_b = {**monde["su"], "X-Company-Id": str(monde["b"])}
    lecteur = monde["lecteur"]
    # Rattacher un compte existant à la société B.
    r = client.post(
        "/auth/users/attach",
        headers=su_b,
        json={"email": lecteur["email"], "role_ids": [monde["admin_role"]]},
    )
    assert r.status_code == 201 and r.json()["multi_company"] is True
    assert (
        client.post(
            "/auth/users/attach",
            headers=su_b,
            json={"email": lecteur["email"], "role_ids": [monde["admin_role"]]},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/auth/users/attach",
            headers=su_b,
            json={"email": "inconnu@test.fr", "role_ids": [monde["admin_role"]]},
        ).status_code
        == 404
    )

    h = login(client, monde["admin"]["email"], monde["a"])
    assert (
        client.post(
            f"/auth/users/{lecteur['id']}/password",
            headers=h,
            json={"new_password": "je-prends-le-controle-1"},
        ).status_code
        == 403
    )
    assert (
        client.patch(f"/auth/users/{lecteur['id']}", headers=h, json={"full_name": "X"}).status_code
        == 403
    )
    # Mais il gère toujours ses rôles DANS A, sans toucher à ceux de B.
    assert (
        client.put(
            f"/auth/users/{lecteur['id']}/roles", headers=h, json={"role_ids": []}
        ).status_code
        == 200
    )
    assert client.get("/auth/users", headers=su_b).json()[0]["id"] == lecteur["id"]
    # Un utilisateur d'une autre société est invisible depuis A.
    assert client.get(f"/auth/users/{lecteur['id']}", headers=h).status_code == 404
    # Le super-administrateur, lui, peut tout.
    assert (
        client.patch(
            f"/auth/users/{lecteur['id']}", headers=su_b, json={"full_name": "Par le super-admin"}
        ).status_code
        == 200
    )


def test_gestion_des_roles(client, monde):
    su = monde["su"]
    r = client.post(
        "/auth/roles",
        headers=su,
        json={"code": f"compta_{uid()}", "name": "Compta", "permissions": ["org:read"]},
    )
    role_id = r.json()["id"]
    r = client.patch(
        f"/auth/roles/{role_id}",
        headers=su,
        json={
            "name": "Comptabilité",
            "description": "Service comptable",
            "permissions": ["org:*", "auth:read"],
        },
    )
    assert r.status_code == 200
    assert (r.json()["name"], r.json()["permissions"]) == ("Comptabilité", ["auth:read", "org:*"])
    assert (
        client.patch(
            f"/auth/roles/{role_id}", headers=su, json={"permissions": ["inventee:x"]}
        ).status_code
        == 400
    )

    # Rôle attribué : pas de suppression. Une fois retiré : suppression possible.
    lecteur = monde["lecteur"]
    client.put(f"/auth/users/{lecteur['id']}/roles", headers=su, json={"role_ids": [role_id]})
    listed = next(x for x in client.get("/auth/roles", headers=su).json() if x["id"] == role_id)
    assert listed["user_count"] == 1
    r = client.delete(f"/auth/roles/{role_id}", headers=su)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "role_utilise")
    client.put(
        f"/auth/users/{lecteur['id']}/roles", headers=su, json={"role_ids": [monde["lecteur_role"]]}
    )
    assert client.delete(f"/auth/roles/{role_id}", headers=su).status_code == 204

    # Le rôle système « admin » est intouchable ; les rôles sont réservés aux super-admins.
    assert (
        client.patch(
            f"/auth/roles/{monde['admin_role']}", headers=su, json={"name": "X"}
        ).status_code
        == 403
    )
    assert client.delete(f"/auth/roles/{monde['admin_role']}", headers=su).status_code == 403
    h = login(client, monde["admin"]["email"], monde["a"])
    assert (
        client.post(
            "/auth/roles", headers=h, json={"code": f"x_{uid()}", "name": "X", "permissions": []}
        ).status_code
        == 403
    )


def test_mot_de_passe_provisoire_a_changer(client, monde):
    """Compte créé ou réinitialisé par un admin : rien n'est accessible avant le changement."""
    h = login(client, monde["admin"]["email"], monde["a"])
    email = f"nouvelle-{uid()}@test.fr"
    r = client.post(
        "/auth/users",
        headers=h,
        json={
            "email": email,
            "full_name": "Nouvelle",
            "password": PASSWORD,
            "role_ids": [monde["gestionnaire_role"]],
        },
    )
    assert r.json()["must_change_password"] is True

    session = client.post("/auth/login", data={"username": email, "password": PASSWORD})
    cookie = session.headers.get_list("set-cookie")[0].split(";")[0]
    new = {
        "Authorization": f"Bearer {session.json()['access_token']}",
        "X-Company-Id": str(monde["a"]),
        "Cookie": cookie,
    }
    # Seul /auth/me répond (le frontend en a besoin pour afficher l'écran de changement).
    assert client.get("/auth/me", headers=new).json()["user"]["must_change_password"] is True
    for method, url in [
        ("get", "/auth/users"),
        ("get", "/org/companies"),
        ("get", "/auth/me/sessions"),
        ("get", "/auth/roles"),
    ]:
        r = getattr(client, method)(url, headers=new)
        assert (r.status_code, r.json()["error"]["code"]) == (403, "mot_de_passe_a_changer"), url
    r = client.patch("/auth/me", headers=new, json={"full_name": "X"})
    assert r.status_code == 403

    # Changement : tout redevient accessible.
    r = client.post(
        "/auth/me/password",
        headers=new,
        json={"current_password": PASSWORD, "new_password": "mon-vrai-mot-de-passe-1"},
    )
    assert r.status_code == 204
    assert client.get("/auth/users", headers=new).status_code == 200
    assert client.get("/auth/me", headers=new).json()["user"]["must_change_password"] is False

    # Une réinitialisation par l'admin remet l'obligation.
    user_id = client.get("/auth/me", headers=new).json()["user"]["id"]
    client.post(
        f"/auth/users/{user_id}/password", headers=h, json={"new_password": "provisoire-numero-2x"}
    )
    again = login(client, email, monde["a"], password="provisoire-numero-2x")
    assert client.get("/auth/users", headers=again).status_code == 403
