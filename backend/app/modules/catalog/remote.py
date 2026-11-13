"""Connexion aux serveurs des fournisseurs : SFTP (SSH), FTPS (FTP + TLS) et FTP.

Précautions, parce qu'on se connecte à des machines extérieures avec des données
saisies par les utilisateurs :
- délais maximum partout (un serveur muet ne bloque pas le worker) ;
- adresses internes refusées par défaut (sinon on pourrait se servir de l'ERP pour
  sonder le réseau du serveur : base de données, Redis, box…) ;
- SFTP : la clé du serveur doit correspondre à l'empreinte confirmée (sinon un
  imposteur pourrait se faire passer pour le fournisseur et recevoir le mot de passe) ;
- FTPS : certificat vérifié ; FTP passif : on ignore l'adresse IP annoncée par le
  serveur (comportement par défaut de ftplib), on reste sur la sienne ;
- taille maximale des fichiers téléchargés.
"""

import base64
import fnmatch
import hashlib
import io
import ipaddress
import socket
import ssl
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from ftplib import FTP, FTP_TLS
from ftplib import all_errors as ftp_errors

import paramiko

from app.core.config import get_settings

TIMEOUT = 20  # secondes


class RemoteError(Exception):
    """Échec de connexion ou de lecture : message destiné à l'utilisateur."""


@dataclass
class RemoteFile:
    name: str
    size: int
    mtime: datetime | None


@dataclass
class SourceConfig:
    protocol: str  # sftp | ftps | ftp
    host: str
    port: int
    username: str
    auth_method: str  # password | key
    secret: str  # mot de passe ou clé privée, en clair (déchiffré juste avant)
    host_key: str | None = None
    tls_verify: bool = True
    remote_dir: str = "/"


def resolve(host: str, port: int) -> str:
    """Adresse IP du serveur, après avoir vérifié qu'elle est publique."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise RemoteError(f"Serveur « {host} » introuvable (nom inconnu)") from exc
    ip = infos[0][4][0]
    address = ipaddress.ip_address(ip)
    if not get_settings().import_allow_private_hosts and not address.is_global:
        raise RemoteError(
            f"« {host} » désigne une adresse interne ({ip}) : refusé pour la sécurité du "
            "serveur (réglage IMPORT_ALLOW_PRIVATE_HOSTS)."
        )
    return ip


def fingerprint(key: paramiko.PKey) -> str:
    """Empreinte au format d'OpenSSH : « ssh-ed25519 SHA256:AbC… »."""
    digest = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")
    return f"{key.get_name()} SHA256:{digest}"


def _load_key(text: str) -> paramiko.PKey:
    for cls in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
        try:
            return cls.from_private_key(io.StringIO(text.strip() + "\n"))
        except (paramiko.SSHException, ValueError):
            continue
    raise RemoteError(
        "Clé privée SSH illisible (format OpenSSH ou PEM attendu, sans phrase de passe)"
    )


def _matches(name: str, pattern: str) -> bool:
    return fnmatch.fnmatch(name.lower(), (pattern or "*").lower())


class _Sftp:
    def __init__(self, cfg: SourceConfig, *, accept_unknown_key: bool):
        ip = resolve(cfg.host, cfg.port)
        try:
            sock = socket.create_connection((ip, cfg.port), timeout=TIMEOUT)
        except OSError as exc:
            raise RemoteError(
                f"Connexion impossible à {cfg.host}:{cfg.port} ({exc.strerror or exc})"
            ) from exc
        self.transport = paramiko.Transport(sock)
        self.transport.banner_timeout = TIMEOUT
        self.transport.auth_timeout = TIMEOUT
        try:
            self.transport.start_client(timeout=TIMEOUT)
            self.host_key = fingerprint(self.transport.get_remote_server_key())
            if cfg.host_key and cfg.host_key != self.host_key:
                raise RemoteError(
                    "L'empreinte du serveur a changé : connexion refusée. Si le fournisseur "
                    f"confirme avoir changé de serveur, testez à nouveau. Reçue : {self.host_key}"
                )
            if not cfg.host_key and not accept_unknown_key:
                raise RemoteError("Empreinte du serveur non confirmée : testez la connexion")
            if cfg.auth_method == "key":
                self.transport.auth_publickey(cfg.username, _load_key(cfg.secret))
            else:
                self.transport.auth_password(cfg.username, cfg.secret)
            self.client = paramiko.SFTPClient.from_transport(self.transport)
            self.client.get_channel().settimeout(TIMEOUT)
        except paramiko.AuthenticationException as exc:
            self.close()
            raise RemoteError("Identifiant ou mot de passe (ou clé) refusé par le serveur") from exc
        except (paramiko.SSHException, OSError, EOFError) as exc:
            self.close()
            raise RemoteError(f"Échec de la connexion SSH : {exc}") from exc
        except RemoteError:
            self.close()
            raise

    def list(self, directory: str, pattern: str) -> list[RemoteFile]:
        try:
            entries = self.client.listdir_attr(directory or ".")
        except OSError as exc:
            raise RemoteError(f"Dossier « {directory} » inaccessible : {exc}") from exc
        return [
            RemoteFile(
                e.filename,
                e.st_size or 0,
                datetime.fromtimestamp(e.st_mtime, UTC) if e.st_mtime else None,
            )
            for e in entries
            if e.st_mode is not None and stat.S_ISREG(e.st_mode) and _matches(e.filename, pattern)
        ]

    def download(self, directory: str, name: str, max_bytes: int) -> bytes:
        path = f"{directory.rstrip('/')}/{name}" if directory else name
        try:
            with self.client.open(path, "rb") as remote:
                remote.prefetch()
                data = remote.read(max_bytes + 1)
        except OSError as exc:
            raise RemoteError(f"Téléchargement de « {name} » impossible : {exc}") from exc
        if len(data) > max_bytes:
            raise RemoteError(f"« {name} » dépasse la taille maximale autorisée")
        return data

    def close(self) -> None:
        self.transport.close()


class _Ftp:
    def __init__(self, cfg: SourceConfig):
        ip = resolve(cfg.host, cfg.port)
        try:
            if cfg.protocol == "ftps":
                context = ssl.create_default_context()
                if not cfg.tls_verify:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                self.ftp: FTP = FTP_TLS(context=context, timeout=TIMEOUT)
                # Par nom (et non par IP) : le certificat est vérifié contre ce nom.
                self.ftp.connect(cfg.host, cfg.port)
                self.ftp.login(cfg.username, cfg.secret)  # FTP_TLS chiffre AVANT le login
                self.ftp.prot_p()  # et chiffre aussi les transferts
            else:
                self.ftp = FTP(timeout=TIMEOUT)
                self.ftp.connect(ip, cfg.port)
                self.ftp.login(cfg.username, cfg.secret)
            self.host_key = None
        except ssl.SSLCertVerificationError as exc:
            raise RemoteError(
                f"Certificat TLS du serveur non valide : {exc.verify_message}"
            ) from exc
        except ftp_errors as exc:
            message = str(exc)
            if message.startswith("530"):
                raise RemoteError("Identifiant ou mot de passe refusé par le serveur") from exc
            raise RemoteError(f"Échec de la connexion FTP : {message}") from exc

    def list(self, directory: str, pattern: str) -> list[RemoteFile]:
        files: list[RemoteFile] = []
        try:
            try:
                # MLSD : liste normalisée (type, taille, date) ; la plupart des serveurs récents.
                for name, facts in self.ftp.mlsd(directory or "", facts=["type", "size", "modify"]):
                    if facts.get("type") == "file" and _matches(name, pattern):
                        modify = facts.get("modify")
                        mtime = (
                            datetime.strptime(modify[:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
                            if modify
                            else None
                        )
                        files.append(RemoteFile(name, int(facts.get("size", 0)), mtime))
            except ftp_errors:
                # Vieux serveur sans MLSD : noms seuls, puis taille et date une par une.
                if directory:
                    self.ftp.cwd(directory)
                for path in self.ftp.nlst():
                    name = path.rsplit("/", 1)[-1]
                    if not _matches(name, pattern):
                        continue
                    try:
                        size = self.ftp.size(name) or 0
                    except ftp_errors:
                        continue  # probablement un dossier
                    mtime = None
                    try:
                        reply = self.ftp.sendcmd(f"MDTM {name}")
                        mtime = datetime.strptime(reply[4:18], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
                    except (ftp_errors, ValueError):
                        pass
                    files.append(RemoteFile(name, size, mtime))
                directory = ""  # déjà dans le dossier
        except ftp_errors as exc:
            raise RemoteError(f"Dossier « {directory} » inaccessible : {exc}") from exc
        self._cwd_done = not directory
        return files

    def download(self, directory: str, name: str, max_bytes: int) -> bytes:
        buffer = bytearray()

        def receive(chunk: bytes) -> None:
            buffer.extend(chunk)
            if len(buffer) > max_bytes:
                raise RemoteError(f"« {name} » dépasse la taille maximale autorisée")

        path = (
            name
            if getattr(self, "_cwd_done", False) or not directory
            else f"{directory.rstrip('/')}/{name}"
        )
        try:
            self.ftp.retrbinary(f"RETR {path}", receive)
        except ftp_errors as exc:
            raise RemoteError(f"Téléchargement de « {name} » impossible : {exc}") from exc
        return bytes(buffer)

    def close(self) -> None:
        try:
            self.ftp.quit()
        except ftp_errors:
            self.ftp.close()


class Connection:
    """`with Connection(cfg) as c: c.list(...)` : se connecte, puis ferme quoi qu'il arrive."""

    def __init__(self, cfg: SourceConfig, *, accept_unknown_key: bool = False):
        self.cfg = cfg
        self.accept_unknown_key = accept_unknown_key

    def __enter__(self) -> "_Sftp | _Ftp":
        if self.cfg.protocol == "sftp":
            self.impl: _Sftp | _Ftp = _Sftp(self.cfg, accept_unknown_key=self.accept_unknown_key)
        else:
            self.impl = _Ftp(self.cfg)
        return self.impl

    def __exit__(self, *exc: object) -> None:
        self.impl.close()
