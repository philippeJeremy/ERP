"""Tests d'intégration : authentification, droits par société, RLS, numérotation, audit.

Chaque test crée ses propres données (codes et e-mails uniques) : pas besoin de
vider la base entre deux exécutions.
"""

import os
import uuid
from datetime import date

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.context import RequestContext
from app.core.db import SessionLocal, set_db_context
from app.core.security import hash_password
from app.main import app
from app.modules.auth.models import User
from app.modules.org import service as org_service
from app.modules.org.schemas import CompanyCreate

pytestmark = pytest.mark.db
PASSWORD = "mot-de-passe-de-test-123"


def uid() -> str:
    return uuid.uuid4().hex[:8].upper()


def owner_conn() -> psycopg.Connection:
    url = os.environ["TEST_MIGRATION_DATABASE_URL"].replace("postgresql+psycopg", "postgresql")
    return psycopg.connect(url, autocommit=True)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def groupe():
    """Un super-admin et deux sociétés A et B (comme le ferait `python -m app.cli bootstrap`)."""
    with SessionLocal() as db:
        admin = User(
            email=f"admin-{uid()}@test.fr",
            full_name="Admin",
            password_hash=hash_password(PASSWORD),
            is_superuser=True,
        )
        db.add(admin)
        db.commit()
        ctx = RequestContext(user_id=admin.id, is_superuser=True)
        a = org_service.create_company(db, ctx, CompanyCreate(code=f"A{uid()}", name="Société A"))
        b = org_service.create_company(db, ctx, CompanyCreate(code=f"B{uid()}", name="Société B"))
        return {"admin_email": admin.email, "admin_id": admin.id, "a": a.id, "b": b.id}


def login(client: TestClient, email: str) -> dict[str, str]:
    r = client.post("/auth/login", data={"username": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_login_et_me(client, groupe):
    h = login(client, groupe["admin_email"])
    me = client.get("/auth/me", headers={**h, "X-Company-Id": str(groupe["a"])}).json()
    assert me["user"]["is_superuser"] is True
    assert {c["company_id"] for c in me["companies"]} >= {groupe["a"], groupe["b"]}
    assert me["permissions"] == ["*"]


def test_mauvais_mot_de_passe(client, groupe):
    r = client.post("/auth/login", data={"username": groupe["admin_email"], "password": "faux"})
    assert r.status_code == 401
    r = client.post("/auth/login", data={"username": "inconnu@test.fr", "password": "faux"})
    assert r.status_code == 401


def test_chaque_societe_voit_ses_sequences(client, groupe):
    h = login(client, groupe["admin_email"])
    seq_a = client.get("/org/sequences", headers={**h, "X-Company-Id": str(groupe["a"])}).json()
    seq_b = client.get("/org/sequences", headers={**h, "X-Company-Id": str(groupe["b"])}).json()
    assert len(seq_a) == len(seq_b) == 5
    assert {s["id"] for s in seq_a}.isdisjoint({s["id"] for s in seq_b})


def test_rls_bloque_les_autres_societes(groupe):
    """Même une requête SQL sans filtre ne voit que la société courante."""
    with SessionLocal() as db:
        set_db_context(db, user_id=groupe["admin_id"], company_id=groupe["a"])
        ids = set(db.scalars(text("SELECT DISTINCT company_id FROM org.number_sequences")))
        assert ids == {groupe["a"]}

        # Écrire dans une autre société est refusé par PostgreSQL (WITH CHECK).
        with pytest.raises(Exception, match="row-level security"):
            db.execute(
                text(
                    "INSERT INTO org.number_sequences (company_id, code, label, prefix) "
                    "VALUES (:b, 'pirate', 'x', 'X-')"
                ),
                {"b": groupe["b"]},
            )
        db.rollback()

        # Sans société courante : rien n'est visible (fermé par défaut).
        set_db_context(db, user_id=groupe["admin_id"], company_id=None)
        assert db.scalar(text("SELECT count(*) FROM org.number_sequences")) == 0


def test_numerotation_par_societe_sans_trou(groupe):
    jour = date(2026, 3, 15)
    with SessionLocal() as db:
        set_db_context(db, user_id=groupe["admin_id"], company_id=groupe["a"])
        assert org_service.next_number(db, "invoice", today=jour) == "FA-2026-00001"
        assert org_service.next_number(db, "invoice", today=jour) == "FA-2026-00002"
        db.commit()

        # Une transaction annulée rend son numéro : pas de trou.
        org_service.next_number(db, "invoice", today=jour)
        db.rollback()
        assert org_service.next_number(db, "invoice", today=jour) == "FA-2026-00003"

        # Nouvelle année : on repart à 1.
        assert org_service.next_number(db, "invoice", today=date(2027, 1, 2)) == "FA-2027-00001"
        db.commit()

        # La société B a son propre compteur.
        set_db_context(db, user_id=groupe["admin_id"], company_id=groupe["b"])
        assert org_service.next_number(db, "invoice", today=jour) == "FA-2026-00001"
        db.commit()


def test_droits_par_societe(client, groupe):
    admin = login(client, groupe["admin_email"])
    in_a = {**admin, "X-Company-Id": str(groupe["a"])}

    # Un rôle « lecteur » et un utilisateur qui l'a seulement dans la société A.
    r = client.post(
        "/auth/roles",
        headers=admin,
        json={"code": f"lecteur_{uid().lower()}", "name": "Lecteur", "permissions": ["org:read"]},
    )
    assert r.status_code == 201, r.text
    email = f"lecteur-{uid()}@test.fr"
    r = client.post(
        "/auth/users",
        headers=in_a,
        json={
            "email": email,
            "full_name": "Lecteur",
            "password": PASSWORD,
            "role_ids": [r.json()["id"]],
        },
    )
    assert r.status_code == 201, r.text

    with owner_conn() as conn:  # mot de passe provisoire considéré comme déjà changé
        conn.execute(
            "UPDATE auth.users SET must_change_password = false WHERE email = %s", (email,)
        )
    user = login(client, email)
    a = {**user, "X-Company-Id": str(groupe["a"])}
    b = {**user, "X-Company-Id": str(groupe["b"])}
    assert client.get("/org/sequences", headers=a).status_code == 200
    assert (
        client.patch(
            f"/org/companies/{groupe['a']}", headers=a, json={"version": 1, "city": "Lyon"}
        ).status_code
        == 403
    )
    assert client.get("/org/sequences", headers=b).status_code == 403  # pas d'accès à B
    assert client.get("/org/sequences", headers=user).status_code == 400  # société requise
    assert [c["id"] for c in client.get("/org/companies", headers=user).json()] == [groupe["a"]]


def test_verrouillage_optimiste(client, groupe):
    h = {**login(client, groupe["admin_email"]), "X-Company-Id": str(groupe["a"])}
    url = f"/org/companies/{groupe['a']}"
    v = client.get(url, headers=h).json()["version"]
    assert client.patch(url, headers=h, json={"version": v, "city": "Lyon"}).status_code == 200
    r = client.patch(url, headers=h, json={"version": v, "city": "Paris"})  # version périmée
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "modifie_entre_temps"


def test_audit_trace_qui_a_fait_quoi(client, groupe):
    h = {**login(client, groupe["admin_email"]), "X-Company-Id": str(groupe["a"])}
    url = f"/org/companies/{groupe['a']}"
    v = client.get(url, headers=h).json()["version"]
    client.patch(url, headers=h, json={"version": v, "city": "Clermont-Ferrand"})
    with owner_conn() as conn:
        row = conn.execute(
            "SELECT user_id, company_id, action, changed_fields, new_data->>'city' "
            "FROM audit.audit_log WHERE table_name = 'companies' AND record_id = %s "
            "ORDER BY id DESC LIMIT 1",
            (str(groupe["a"]),),
        ).fetchone()
        assert row == (groupe["admin_id"], groupe["a"], "UPDATE", ["city"], "Clermont-Ferrand")
        # Le hash du mot de passe n'est jamais copié dans le journal.
        assert (
            conn.execute(
                "SELECT count(*) FROM audit.audit_log WHERE new_data ? 'password_hash'"
            ).fetchone()[0]
            == 0
        )


def test_role_applicatif_ne_peut_ni_falsifier_l_audit_ni_modifier_la_structure():
    with SessionLocal() as db:
        with pytest.raises(Exception, match="permission denied"):
            db.execute(text("DELETE FROM audit.audit_log"))
        db.rollback()
        with pytest.raises(Exception, match="must be owner|permission denied"):
            db.execute(text("DROP TABLE org.companies"))
        db.rollback()
