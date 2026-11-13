"""Tests de la messagerie : réglages SMTP, modèles, envoi des devis, factures,
relances et bons de commande à un vrai serveur SMTP local (aiosmtpd)."""

import io
import os
import socket
from datetime import date, timedelta
from email import message_from_bytes, policy

import pytest
from aiosmtpd.controller import Controller
from facturx import get_facturx_xml_from_pdf
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.main import app
from tests.test_admin_utilisateurs import login, monde, uid  # noqa: F401  (fixture)
from tests.test_facturation import _company_legal, _sold
from tests.test_stock import _order

TODAY = date.today()


class Inbox:
    def __init__(self) -> None:
        self.messages: list = []

    async def handle_DATA(self, server, session, envelope):  # noqa: N802 (API aiosmtpd)
        self.messages.append(
            (envelope.rcpt_tos, message_from_bytes(envelope.content, policy=policy.default))
        )
        return "250 OK"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def smtp():
    inbox = Inbox()
    controller = Controller(inbox, hostname="127.0.0.1", port=_free_port())
    controller.start()
    yield controller, inbox
    controller.stop()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def ok(r, code=200):
    assert r.status_code == code, r.text
    return r.json()


def _configure(client, su, port):
    return ok(
        client.put(
            "/mail/smtp",
            headers=su,
            json={
                "host": "127.0.0.1",
                "port": port,
                "security": "none",
                "from_email": "factures@exemple.example.com",
                "from_name": "Holding Pneus",
                "reply_to": "compta@exemple.example.com",
                "bcc": "archive@exemple.example.com",
            },  # fmt: skip
        )
    )


def _attachment(message):
    part = next(message.iter_attachments())
    return part.get_filename(), part.get_content()


@pytest.mark.db
def test_messagerie(client, monde, smtp):  # noqa: F811
    controller, inbox = smtp
    su = monde["su"]
    s = int(uid(), 16) % 10**8
    supplier, tire, site, customer, order = _sold(client, su, s)
    cid = customer["id"]
    ok(
        client.patch(
            f"/partners/{cid}",
            headers=su,
            json={"version": customer["version"], "invoice_email": "compta@garage.example.com"},
        )
    )
    ok(
        client.post(
            f"/partners/{cid}/contacts",
            headers=su,
            json={
                "last_name": "Martin",
                "first_name": "Paul",
                "email": "paul@garage.example.com",
                "is_primary": True,
            },
        ),
        201,
    )
    _company_legal(client, su, monde["a"])
    invoice = ok(
        client.post(
            "/billing/invoices/from-deliveries",
            headers=su,
            json={"delivery_ids": [d["id"] for d in order["deliveries"]], "issue": True},
        )
    )[0]
    iid = invoice["id"]

    # --- Sans réglages : brouillon proposé, mais l'envoi est refusé clairement.
    draft = ok(client.get(f"/billing/invoices/{iid}/email", headers=su))
    assert draft["smtp_ready"] is False and draft["to"] == ["compta@garage.example.com"]
    assert {x["email"] for x in draft["suggestions"]} == {
        "compta@garage.example.com",
        "paul@garage.example.com",
    }
    assert invoice["number"] in draft["subject"] and "Factur-X" in draft["body"]
    send = {"to": draft["to"], "subject": draft["subject"], "body": draft["body"]}
    r = client.post(f"/billing/invoices/{iid}/email", headers=su, json=send)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "mail_impossible")

    # --- Réglages + mail d'essai.
    settings = _configure(client, su, controller.port)
    assert settings["configured"] and settings["has_password"] is False
    test = ok(client.post("/mail/smtp/test", headers=su, json={"to": "moi@exemple.example.com"}))
    assert test["status"] == "envoye"
    assert inbox.messages[-1][1]["Subject"].startswith("Test d'envoi")

    # --- Facture : PDF Factur-X joint, copie cachée d'archivage, Reply-To.
    sent = ok(
        client.post(
            f"/billing/invoices/{iid}/email",
            headers=su,
            json={**send, "cc": ["chef@garage.example.com"]},
        )
    )
    assert sent["sent_at"] is not None
    rcpt, mail = inbox.messages[-1]
    assert set(rcpt) == {
        "compta@garage.example.com",
        "chef@garage.example.com",
        "archive@exemple.example.com",
    }
    assert "Bcc" not in mail and mail["Reply-To"] == "compta@exemple.example.com"
    assert "Holding Pneus" in mail["From"] and mail["Subject"] == draft["subject"]
    name, content = _attachment(mail)
    assert name == f"Facture {invoice['number']}.pdf" and content.startswith(b"%PDF")
    assert get_facturx_xml_from_pdf(io.BytesIO(content))[0] == "factur-x.xml"
    history = ok(client.get(f"/billing/invoices/{iid}/email", headers=su))["history"]
    assert history[0]["status"] == "envoye" and history[0]["attachments"][0]["filename"] == name
    stored = client.get(f"/mail/messages/{history[0]['id']}/attachments/0", headers=su)
    assert stored.status_code == 200 and stored.content == content

    # --- Modèle personnalisé, puis retour au modèle par défaut.
    ok(
        client.put(
            "/mail/templates/facture",
            headers=su,
            json={
                "subject": "Votre facture {numero} ({montant_ttc})",
                "body": "Bonjour {destinataire}, {inconnu}.",
            },
        )
    )
    draft = ok(client.get(f"/billing/invoices/{iid}/email", headers=su))
    assert draft["subject"].startswith(f"Votre facture {invoice['number']} (")
    assert draft["body"] == f"Bonjour Garage Facture {s}, {{inconnu}}."
    templates = ok(client.get("/mail/templates", headers=su))
    assert next(t for t in templates if t["kind"] == "facture")["customized"] is True
    assert ok(client.delete("/mail/templates/facture", headers=su))["customized"] is False

    # --- Devis : le brouillon passe en « envoyé ».
    quote = ok(
        client.post("/sales/quotes", headers=su, json={"customer_id": cid, "site_id": site}), 201
    )
    ok(
        client.post(
            f"/sales/quotes/{quote['id']}/lines",
            headers=su,
            json={"article_id": tire, "quantity": "2"},
        )
    )
    draft = ok(client.get(f"/sales/quotes/{quote['id']}/email", headers=su))
    assert draft["to"] == ["paul@garage.example.com"]  # contact principal pour un devis
    quote = ok(
        client.post(
            f"/sales/quotes/{quote['id']}/email",
            headers=su,
            json={"to": draft["to"], "subject": draft["subject"], "body": draft["body"]},
        )
    )
    assert quote["status"] == "envoye"
    assert _attachment(inbox.messages[-1][1])[0] == f"Devis {quote['number']}.pdf"

    # --- Bon de commande fournisseur.
    po = _order(client, su, supplier, site, [(tire, 4, "60", 0)])
    draft = ok(client.get(f"/purchasing/orders/{po['id']}/email", headers=su))
    assert po["number"] in draft["subject"]
    po = ok(
        client.post(
            f"/purchasing/orders/{po['id']}/email",
            headers=su,
            json={
                "to": ["commandes@fournisseur.example.com"],
                "subject": draft["subject"],
                "body": draft["body"],
            },
        )
    )
    assert po["status"] == "envoyee"
    assert _attachment(inbox.messages[-1][1])[0] == f"Commande {po['number']}.pdf"

    # --- Relance par mail d'une facture en retard.
    r = client.get(f"/billing/customers/{cid}/reminder-email", headers=su)
    assert r.status_code == 422  # rien en retard
    owner = create_engine(os.environ["TEST_MIGRATION_DATABASE_URL"])
    with owner.begin() as conn:
        conn.execute(text("ALTER TABLE billing.invoices DISABLE TRIGGER protect_issued"))
        conn.execute(
            text("UPDATE billing.invoices SET due_date = :d WHERE id = :i"),
            {"d": TODAY - timedelta(days=10), "i": iid},
        )
        conn.execute(text("ALTER TABLE billing.invoices ENABLE TRIGGER protect_issued"))
    owner.dispose()
    draft = ok(client.get(f"/billing/customers/{cid}/reminder-email", headers=su))
    assert draft["subject"].startswith("Rappel d'échéance") and invoice["number"] in draft["body"]
    ok(
        client.post(
            f"/billing/customers/{cid}/reminder-email",
            headers=su,
            json={"to": draft["to"], "subject": draft["subject"], "body": draft["body"]},
        )
    )
    assert ok(client.get(f"/billing/invoices/{iid}", headers=su))["reminder_count"] == 1
    assert _attachment(inbox.messages[-1][1])[0] == "Relance.pdf"
    draft = ok(client.get(f"/billing/customers/{cid}/reminder-email", headers=su))
    assert draft["subject"].startswith("Deuxième relance")

    # --- Serveur injoignable : échec noté, puis nouvel essai réussi.
    _configure(client, su, _free_port())
    r = client.post("/mail/smtp/test", headers=su, json={"to": "moi@exemple.example.com"})
    assert r.status_code == 422 and "Envoi impossible" in r.json()["error"]["message"]
    ok(client.post(f"/billing/invoices/{iid}/email", headers=su, json=send))
    failed = ok(
        client.get(
            f"/mail/messages?status=echec&document_type=invoice&document_id={iid}", headers=su
        )
    )
    assert failed["total"] == 1 and failed["items"][0]["error"]
    _configure(client, su, controller.port)
    retried = ok(client.post(f"/mail/messages/{failed['items'][0]['id']}/retry", headers=su))
    assert retried["status"] == "envoye" and retried["attempts"] == 2

    # --- Droits : les réglages sont réservés.
    user_id = monde["gestionnaire"]["id"]
    client.put(
        f"/auth/users/{user_id}/companies/{monde['a']}/permissions",
        headers=su,
        json={"permissions": ["billing:read", "mail:read"]},
    )
    reader = login(client, monde["gestionnaire"]["email"], monde["a"])
    assert client.get("/mail/smtp", headers=reader).status_code == 403
    assert client.get("/mail/messages", headers=reader).status_code == 200
    assert (
        client.post(f"/billing/invoices/{iid}/email", headers=reader, json=send).status_code == 403
    )
    in_b = {**su, "X-Company-Id": str(monde["b"])}
    assert ok(client.get("/mail/messages", headers=in_b))["total"] == 0


@pytest.mark.db
def test_identifiant_sans_auth(client, monde, smtp):  # noqa: F811
    """Un serveur sans AUTH : message clair plutôt qu'une erreur STARTTLS trompeuse."""
    controller, _inbox = smtp
    su = monde["su"]
    body = {
        "host": "127.0.0.1", "port": controller.port, "security": "none",
        "username": "erp", "from_email": "factures@exemple.example.com",
    }  # fmt: skip
    ok(client.put("/mail/smtp", headers=su, json=body))
    r = client.post("/mail/smtp/test", headers=su, json={"to": "moi@exemple.example.com"})
    assert r.status_code == 422 and "identifiant" in r.json()["error"]["message"], r.text
