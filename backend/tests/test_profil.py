"""Tests de la page de profil : nom, mot de passe, sessions actives."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.main import app
from app.modules.auth.models import User
from tests.test_sessions import call_refresh, refresh_cookie

pytestmark = pytest.mark.db
PASSWORD = "mot-de-passe-de-test-123"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def email() -> str:
    with SessionLocal() as db:
        user = User(
            email=f"profil-{uuid.uuid4().hex[:8]}@test.fr",
            full_name="Avant",
            password_hash=hash_password(PASSWORD),
        )
        db.add(user)
        db.commit()
        return user.email


def open_session(client: TestClient, email: str, password: str = PASSWORD) -> dict:
    """Connexion : renvoie les en-têtes à envoyer (jeton d'accès + cookie de session)."""
    r = client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"User-Agent": f"Navigateur-{uuid.uuid4().hex[:4]}"},
    )
    assert r.status_code == 200, r.text
    return {
        "Authorization": f"Bearer {r.json()['access_token']}",
        "Cookie": f"erp_refresh={refresh_cookie(r)}",
    }


def test_modifier_son_nom(client, email):
    h = open_session(client, email)
    r = client.patch("/auth/me", headers=h, json={"full_name": "Jérémy Philippe"})
    assert r.status_code == 200
    assert client.get("/auth/me", headers=h).json()["user"]["full_name"] == "Jérémy Philippe"
    assert client.patch("/auth/me", headers=h, json={"full_name": ""}).status_code == 422


def test_sessions_actives(client, email):
    pc = open_session(client, email)
    open_session(client, email)  # un deuxième appareil
    sessions = client.get("/auth/me/sessions", headers=pc).json()
    assert len(sessions) == 2
    assert [s["current"] for s in sessions].count(True) == 1

    # Fermer l'autre appareil depuis le PC.
    other = next(s for s in sessions if not s["current"])
    assert client.delete(f"/auth/me/sessions/{other['id']}", headers=pc).status_code == 204
    assert len(client.get("/auth/me/sessions", headers=pc).json()) == 1
    # Fermer une session inconnue (ou celle d'un autre utilisateur) : 404.
    assert client.delete(f"/auth/me/sessions/{uuid.uuid4()}", headers=pc).status_code == 404


def test_deconnecter_les_autres_sessions(client, email):
    pc = open_session(client, email)
    phone = open_session(client, email)
    assert client.post("/auth/me/sessions/revoke-others", headers=pc).status_code == 204
    phone_cookie = phone["Cookie"].split("=", 1)[1]
    assert call_refresh(client, phone_cookie).status_code == 401  # le téléphone est déconnecté
    pc_cookie = pc["Cookie"].split("=", 1)[1]
    assert call_refresh(client, pc_cookie).status_code == 200  # le PC reste connecté


def test_changer_son_mot_de_passe(client, email):
    pc = open_session(client, email)
    phone = open_session(client, email)
    new = "nouveau-mot-de-passe-456"

    r = client.post(
        "/auth/me/password", headers=pc, json={"current_password": "faux", "new_password": new}
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "mot_de_passe_incorrect"
    r = client.post(
        "/auth/me/password",
        headers=pc,
        json={"current_password": PASSWORD, "new_password": "court"},
    )
    assert r.status_code == 422

    r = client.post(
        "/auth/me/password", headers=pc, json={"current_password": PASSWORD, "new_password": new}
    )
    assert r.status_code == 204
    # Les autres sessions sont fermées, celle-ci reste ouverte.
    assert call_refresh(client, phone["Cookie"].split("=", 1)[1]).status_code == 401
    assert call_refresh(client, pc["Cookie"].split("=", 1)[1]).status_code == 200
    # Ancien mot de passe refusé, nouveau accepté.
    assert (
        client.post("/auth/login", data={"username": email, "password": PASSWORD}).status_code
        == 401
    )
    open_session(client, email, new)
