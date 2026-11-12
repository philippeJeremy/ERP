"""Tests des sessions : refresh token en cookie httpOnly, rotation, vol, déconnexion."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.main import app
from app.modules.auth.models import User
from tests.test_multisociete import owner_conn

pytestmark = pytest.mark.db
PASSWORD = "mot-de-passe-de-test-123"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def email() -> str:
    with SessionLocal() as db:
        user = User(
            email=f"session-{uuid.uuid4().hex[:8]}@test.fr",
            full_name="Session",
            password_hash=hash_password(PASSWORD),
        )
        db.add(user)
        db.commit()
        return user.email


def refresh_cookie(response) -> str:
    """Valeur du cookie erp_refresh posé par la réponse (lu dans l'en-tête Set-Cookie)."""
    header = next(
        h for h in response.headers.get_list("set-cookie") if h.startswith("erp_refresh=")
    )
    return header.split(";", 1)[0].split("=", 1)[1]


def call_refresh(client: TestClient, token: str):
    # Le cookie est limité au chemin /api/auth (vu du navigateur) : en test, on parle
    # directement à l'API (sans le /api de Caddy), donc on l'envoie à la main.
    return client.post("/auth/refresh", headers={"Cookie": f"erp_refresh={token}"})


def login(client: TestClient, email: str):
    r = client.post("/auth/login", data={"username": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r


def test_login_pose_un_cookie_securise(client, email):
    r = login(client, email)
    header = next(h for h in r.headers.get_list("set-cookie") if h.startswith("erp_refresh="))
    attrs = header.lower()
    assert "httponly" in attrs
    assert "secure" in attrs
    assert "samesite=strict" in attrs
    assert "path=/api/auth" in attrs
    assert r.json()["access_token"]


def test_rotation(client, email):
    t1 = refresh_cookie(login(client, email))
    r = call_refresh(client, t1)
    assert r.status_code == 200
    t2 = refresh_cookie(r)
    assert t2 != t1
    # Le nouveau jeton d'accès fonctionne.
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.status_code == 200

    # Deux onglets en même temps : l'ancien jeton, rejoué tout de suite, est refusé
    # SANS révoquer la session…
    assert call_refresh(client, t1).status_code == 401
    # … donc le nouveau marche toujours.
    assert call_refresh(client, t2).status_code == 200


def test_jeton_vole_rejoue_plus_tard_revoque_toute_la_session(client, email):
    t1 = refresh_cookie(login(client, email))
    t2 = refresh_cookie(call_refresh(client, t1))
    # On simule le passage du temps : t1 a été remplacé il y a une minute.
    with owner_conn() as conn:
        conn.execute(
            "UPDATE auth.refresh_tokens SET revoked_at = revoked_at - interval '1 minute' "
            "WHERE revoked_reason = 'rotated' AND user_id = "
            "(SELECT id FROM auth.users WHERE email = %s)",
            (email,),
        )
    # Le voleur rejoue t1 : refusé, et toute la famille est révoquée…
    assert call_refresh(client, t1).status_code == 401
    # … y compris le jeton légitime de l'utilisateur, qui devra se reconnecter.
    assert call_refresh(client, t2).status_code == 401
    with owner_conn() as conn:
        reasons = {
            r[0]
            for r in conn.execute(
                "SELECT revoked_reason FROM auth.refresh_tokens t JOIN auth.users u "
                "ON u.id = t.user_id WHERE u.email = %s",
                (email,),
            )
        }
    assert reasons == {"rotated", "reuse"}


def test_deconnexion(client, email):
    t1 = refresh_cookie(login(client, email))
    r = client.post("/auth/logout", headers={"Cookie": f"erp_refresh={t1}"})
    assert r.status_code == 204
    assert (
        'erp_refresh=""' in r.headers["set-cookie"]
        or "max-age=0" in r.headers["set-cookie"].lower()
    )
    assert call_refresh(client, t1).status_code == 401


def test_refresh_sans_cookie(client):
    assert client.post("/auth/refresh").status_code == 401
    assert call_refresh(client, "n-importe-quoi").status_code == 401


def test_compte_desactive(client, email):
    t1 = refresh_cookie(login(client, email))
    with owner_conn() as conn:
        conn.execute("UPDATE auth.users SET is_active = false WHERE email = %s", (email,))
    assert call_refresh(client, t1).status_code == 401
