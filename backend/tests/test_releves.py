"""Tests des relèves automatiques : vrais serveurs SFTP et FTP locaux."""

import os
import time

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core import secrets
from app.core.config import get_settings
from app.main import app
from app.modules.catalog import poller
from app.modules.catalog.remote import RemoteError, resolve
from tests.remote_servers import PASSWORD, USER, FtpServer, SftpServer
from tests.test_admin_utilisateurs import monde, uid  # noqa: F401  (fixture)
from tests.test_catalogue import _csv, ean


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "secrets_key", SecretStr(Fernet.generate_key().decode()))
    return s


def test_adresses_internes_refusees():
    assert get_settings().import_allow_private_hosts is False
    for host in ("127.0.0.1", "localhost", "10.0.0.5", "192.168.1.1", "169.254.169.254"):
        with pytest.raises(RemoteError, match="interne"):
            resolve(host, 22)


def test_chiffrement(settings):
    token = secrets.encrypt("mot de passe")
    assert "mot de passe" not in token
    assert secrets.decrypt(token) == "mot de passe"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def local_hosts(settings, monkeypatch):
    # Les serveurs de test tournent sur 127.0.0.1 : on lève exceptionnellement l'interdiction.
    monkeypatch.setattr(settings, "import_allow_private_hosts", True)


def _supplier_and_profile(client, su, s):
    supplier = client.post("/partners", headers=su, json={"name": f"Distrib {s}"}).json()["id"]
    profile = client.post(
        "/catalog/import-profiles",
        headers=su,
        json={"partner_id": supplier, "file_format": "csv", "delimiter": ";",
              "mapping": {"supplier_ref": "Réf fournisseur", "ean": "EAN", "brand": "Marque",
                          "designation": "Désignation", "purchase_price": "Prix net HT"}},
    ).json()["id"]  # fmt: skip
    return supplier, profile


def _source(client, su, source_id):
    return _source(client, su, source_id)


def _write(path, rows, mtime=None):
    with open(path, "wb") as f:
        f.write(_csv(rows))
    if mtime:
        os.utime(path, (mtime, mtime))


@pytest.mark.db
def test_releve_sftp(client, monde, local_hosts, tmp_path):  # noqa: F811
    su = monde["su"]
    s = int(uid(), 16) % 10**7
    supplier, profile = _supplier_and_profile(client, su, s)
    rows = [
        [f"S{s}-{i}", ean(s * 10 + i), "Michelin", f"205/55 R16 91V n°{i}", f"{60 + i},00"]
        for i in range(3)
    ]
    _write(tmp_path / "tarif_novembre.csv", rows, time.time() - 3600)
    _write(tmp_path / "lisezmoi.txt", [])
    server = SftpServer(str(tmp_path))
    try:
        conn = {"protocol": "sftp", "host": "127.0.0.1", "port": server.port, "username": USER,
                "remote_dir": "/", "pattern": "tarif_*.csv"}  # fmt: skip
        # Mauvais mot de passe → message clair.
        r = client.post("/catalog/import-sources/test", headers=su, json={**conn, "secret": "faux"})
        assert r.status_code == 422 and "refusé" in r.json()["error"]["message"]
        # Bon mot de passe : empreinte du serveur + fichiers correspondant au motif.
        r = client.post(
            "/catalog/import-sources/test", headers=su, json={**conn, "secret": PASSWORD}
        )
        assert r.status_code == 200, r.text
        test = r.json()
        assert test["host_key"].startswith("ecdsa-sha2-nistp256 SHA256:")
        assert [f["name"] for f in test["files"]] == ["tarif_novembre.csv"]

        source_in = {**conn, "secret": PASSWORD, "partner_id": supplier, "profile_id": profile,
                     "name": "SFTP", "interval_hours": 6}  # fmt: skip
        # Sans empreinte confirmée : refusé.
        assert client.post("/catalog/import-sources", headers=su, json=source_in).status_code == 422
        r = client.post(
            "/catalog/import-sources", headers=su, json={**source_in, "host_key": test["host_key"]}
        )
        assert r.status_code == 201, r.text
        source = r.json()
        assert source["has_secret"] and "secret" not in source and source["next_check_at"]

        # Relève : le fichier est analysé, en attente de validation (pas d'application auto).
        client.post(f"/catalog/import-sources/{source['id']}/run", headers=su)
        source = client.get("/catalog/import-sources", headers=su).json()
        source = next(x for x in source if x["name"] == "SFTP" and x["partner_id"] == supplier)
        assert source["last_status"] == "ok", source
        assert "en attente de validation" in source["last_message"]
        run = client.get(f"/catalog/imports/{source['last_run_id']}", headers=su).json()
        assert (run["status"], run["source"], run["new_count"]) == ("pret", "sftp", 3)

        # Même fichier : rien de nouveau.
        client.post(f"/catalog/import-sources/{source['id']}/run", headers=su)
        again = client.get("/catalog/import-sources", headers=su).json()
        again = next(x for x in again if x["id"] == source["id"])
        assert again["last_status"] == "aucun_fichier"

        # Nouveau fichier + application automatique activée → appliqué tout seul.
        client.post(f"/catalog/imports/{run['id']}/cancel", headers=su)
        rows[0][4] = "61,50"
        _write(tmp_path / "tarif_decembre.csv", rows)
        r = client.put(
            f"/catalog/import-sources/{source['id']}",
            headers=su,
            json={**source_in, "secret": None, "host_key": test["host_key"], "auto_apply": True},
        )
        assert r.status_code == 200, r.text
        client.post(f"/catalog/import-sources/{source['id']}/run", headers=su)
        done = next(
            x
            for x in client.get("/catalog/import-sources", headers=su).json()
            if x["id"] == source["id"]
        )
        assert "appliqué automatiquement" in done["last_message"], done
        run = client.get(f"/catalog/imports/{done['last_run_id']}", headers=su).json()
        assert (run["status"], run["filename"]) == ("termine", "tarif_decembre.csv")

        # Le serveur change de clé (imposteur ?) → relève refusée.
        server.host_key = __import__("paramiko").ECDSAKey.generate()
        _write(tmp_path / "tarif_janvier.csv", rows)
        client.post(f"/catalog/import-sources/{source['id']}/run", headers=su)
        bad = next(
            x
            for x in client.get("/catalog/import-sources", headers=su).json()
            if x["id"] == source["id"]
        )
        assert bad["last_status"] == "erreur" and "empreinte" in bad["last_message"]
    finally:
        server.close()

    # Société B : relèves de A invisibles.
    in_b = {**su, "X-Company-Id": str(monde["b"])}
    assert all(
        x["partner_id"] != supplier
        for x in client.get("/catalog/import-sources", headers=in_b).json()
    )


@pytest.mark.db
def test_releve_ftp_planifiee(client, monde, local_hosts, tmp_path):  # noqa: F811
    su = monde["su"]
    s = int(uid(), 16) % 10**7
    supplier, profile = _supplier_and_profile(client, su, s)
    rows = [
        [f"F{s}-{i}", ean(s * 10 + 5 + i), "Pirelli", f"225/45 R17 94Y n°{i}", "90"]
        for i in range(2)
    ]
    os.makedirs(tmp_path / "tarifs")
    _write(tmp_path / "tarifs" / "TARIF.CSV", rows)
    server = FtpServer(str(tmp_path))
    try:
        r = client.post(
            "/catalog/import-sources",
            headers=su,
            json={"protocol": "ftp", "host": "127.0.0.1", "port": server.port, "username": USER,
                  "secret": PASSWORD, "remote_dir": "/tarifs", "pattern": "tarif*.csv",
                  "partner_id": supplier, "profile_id": profile, "auto_apply": True},
        )  # fmt: skip
        assert r.status_code == 201, r.text
        source_id = r.json()["id"]
        # Le cron du worker : la relève est due (next_check_at = maintenant) dans la société A.
        assert poller.poll_due_sources() >= 1
        source = next(
            x
            for x in client.get("/catalog/import-sources", headers=su).json()
            if x["id"] == source_id
        )
        assert "appliqué automatiquement" in source["last_message"], source
        # Prochaine relève dans 24 h : un nouveau passage du cron ne la reprend pas.
        poller.poll_due_sources()
        after = next(
            x
            for x in client.get("/catalog/import-sources", headers=su).json()
            if x["id"] == source_id
        )
        assert after["last_check_at"] == source["last_check_at"]
        links = client.get(f"/catalog/article-suppliers?partner_id={supplier}", headers=su).json()
        assert links["total"] == 2
    finally:
        server.close()


@pytest.mark.db
def test_sans_cle_de_chiffrement(client, monde, monkeypatch):  # noqa: F811
    monkeypatch.setattr(get_settings(), "secrets_key", None)
    su = monde["su"]
    assert client.get("/catalog/import-sources/settings", headers=su).json() == {
        "secrets_configured": False
    }
    supplier, profile = _supplier_and_profile(client, su, int(uid(), 16) % 10**7)
    r = client.post(
        "/catalog/import-sources",
        headers=su,
        json={"protocol": "ftps", "host": "ftp.exemple.fr", "username": "u", "secret": "p",
              "partner_id": supplier, "profile_id": profile},
    )  # fmt: skip
    assert (r.status_code, r.json()["error"]["code"]) == (503, "chiffrement_non_configure")


def test_cle_ssh(local_hosts, tmp_path):
    """Authentification SFTP par clé privée (OpenSSH, ed25519)."""
    import paramiko
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    from app.modules.catalog.remote import Connection, SourceConfig

    private = ed25519.Ed25519PrivateKey.generate()
    text = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.OpenSSH,
        serialization.NoEncryption(),
    ).decode()
    key = paramiko.Ed25519Key.from_private_key(__import__("io").StringIO(text))
    (tmp_path / "tarif.csv").write_text("x")
    server = SftpServer(str(tmp_path), authorized_key=key)
    try:
        cfg = SourceConfig("sftp", "127.0.0.1", server.port, USER, "key", text)
        with Connection(cfg, accept_unknown_key=True) as remote:
            assert [f.name for f in remote.list("/", "*.csv")] == ["tarif.csv"]
            assert remote.download("/", "tarif.csv", 100) == b"x"
            with pytest.raises(RemoteError, match="taille"):
                remote.download("/", "tarif.csv", 0)
        # Empreinte non confirmée : refus en relève normale.
        with pytest.raises(RemoteError, match="non confirmée"), Connection(cfg):
            pass
    finally:
        server.close()
