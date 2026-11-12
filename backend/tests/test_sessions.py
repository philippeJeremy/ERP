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


# --- Durée des sessions : inactivité (30 min) et durée maximale (12 h) --------------


def session_row(email: str):
    with owner_conn() as conn:
        return conn.execute(
            "SELECT t.session_started_at, t.expires_at, now() FROM auth.refresh_tokens t "
            "JOIN auth.users u ON u.id = t.user_id WHERE u.email = %s AND t.revoked_at IS NULL",
            (email,),
        ).fetchone()


def test_expiration_apres_inactivite(client, email):
    r = login(client, email)
    started, expires, now = session_row(email)
    # Le jeton expire 30 min après sa création (expiration « glissante »).
    assert 29 * 60 < (expires - now).total_seconds() <= 30 * 60
    # Le cookie, lui, vit jusqu'à la fin ABSOLUE de la session (12 h).
    header = next(h for h in r.headers.get_list("set-cookie") if h.startswith("erp_refresh="))
    assert "max-age=4319" in header.lower() or "max-age=4320" in header.lower()

    # 31 minutes sans aucune requête…
    with owner_conn() as conn:
        conn.execute(
            "UPDATE auth.refresh_tokens SET expires_at = now() - interval '1 minute' "
            "WHERE user_id = (SELECT id FROM auth.users WHERE email = %s)",
            (email,),
        )
    # … la session est terminée.
    assert call_refresh(client, refresh_cookie(r)).status_code == 401


def test_renouvellement_repousse_l_echeance_sans_depasser_12h(client, email):
    t = refresh_cookie(login(client, email))
    # La session a commencé il y a 11 h 50 : il ne reste que 10 minutes.
    with owner_conn() as conn:
        conn.execute(
            "UPDATE auth.refresh_tokens "
            "SET session_started_at = now() - interval '11 hours 50 minutes' "
            "WHERE user_id = (SELECT id FROM auth.users WHERE email = %s)",
            (email,),
        )
    r = call_refresh(client, t)
    assert r.status_code == 200
    started, expires, now = session_row(email)
    # Échéance plafonnée à la fin de session (10 min), pas maintenant + 30 min.
    assert (expires - now).total_seconds() <= 10 * 60 + 5


def test_duree_maximale_atteinte(client, email):
    t = refresh_cookie(login(client, email))
    # Session commencée il y a 12 h 01, jeton pourtant encore « frais ».
    with owner_conn() as conn:
        conn.execute(
            "UPDATE auth.refresh_tokens "
            "SET session_started_at = now() - interval '12 hours 1 minute' "
            "WHERE user_id = (SELECT id FROM auth.users WHERE email = %s)",
            (email,),
        )
    assert call_refresh(client, t).status_code == 401


def test_me_indique_le_delai_d_inactivite(client, email):
    token = login(client, email).json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["session_idle_minutes"] == 30
