"""Envoi réel d'un mail par SMTP (bibliothèque standard smtplib)."""

import ipaddress
import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from app.core.config import get_settings

TIMEOUT = 20  # secondes : un serveur muet ne bloque pas le worker


class SendError(Exception):
    pass


def check_host(host: str, port: int) -> None:
    """Refuse un serveur sur le réseau interne (sauf SMTP_ALLOW_PRIVATE_HOSTS=true)."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SendError(f"Serveur « {host} » introuvable (nom inconnu)") from exc
    ip = ipaddress.ip_address(infos[0][4][0])
    if not get_settings().smtp_allow_private_hosts and not ip.is_global:
        raise SendError(
            f"« {host} » désigne une adresse interne ({ip}) : refusé pour la sécurité du "
            "serveur (réglage SMTP_ALLOW_PRIVATE_HOSTS)."
        )


def build(
    *,
    from_email: str,
    from_name: str | None,
    to: list[str],
    cc: list[str],
    reply_to: str | None,
    subject: str,
    body: str,
    attachments: list[tuple[str, str, bytes]],
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = formataddr((from_name or "", from_email))
    message["To"] = ", ".join(to)
    if cc:
        message["Cc"] = ", ".join(cc)
    if reply_to:
        message["Reply-To"] = reply_to
    message["Subject"] = subject
    message["Message-ID"] = make_msgid(domain=from_email.split("@")[-1])
    message.set_content(body)
    for filename, content_type, content in attachments:
        main, _, sub = content_type.partition("/")
        message.add_attachment(
            content, maintype=main, subtype=sub or "octet-stream", filename=filename
        )
    return message


def deliver(
    *,
    host: str,
    port: int,
    security: str,
    username: str | None,
    password: str | None,
    message: EmailMessage,
    recipients: list[str],
) -> None:
    check_host(host, port)
    context = ssl.create_default_context()
    try:
        if security == "ssl":
            server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=TIMEOUT)
        with server:
            server.ehlo()
            if security == "starttls":
                if not server.has_extn("starttls"):
                    raise SendError("Le serveur ne propose pas STARTTLS : essayez SSL (port 465)")
                server.starttls(context=context)
                server.ehlo()
            if username:
                if not server.has_extn("auth"):
                    raise SendError(
                        "Le serveur n'accepte pas d'identifiant sur cette connexion : "
                        "videz l'identifiant ou choisissez une connexion chiffrée"
                    )
                server.login(username, password or "")
            server.send_message(message, to_addrs=recipients)
    except smtplib.SMTPAuthenticationError as exc:
        raise SendError("Identifiant ou mot de passe refusé par le serveur de mail") from exc
    except smtplib.SMTPRecipientsRefused as exc:
        raise SendError(
            "Adresse(s) refusée(s) par le serveur : " + ", ".join(exc.recipients)
        ) from exc
    except ssl.SSLError as exc:
        raise SendError(f"Échec de la connexion chiffrée : {exc.reason or exc}") from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise SendError(f"Envoi impossible : {exc}") from exc
