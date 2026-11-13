"""Chiffrement des secrets stockés en base (mots de passe, clés SSH des fournisseurs).

Fernet (bibliothèque `cryptography`) : AES-128 + HMAC-SHA256. Le texte chiffré est
illisible et infalsifiable sans la clé SECRETS_KEY, qui n'est que dans l'environnement
du serveur : une copie de la base (sauvegarde volée…) ne livre pas les mots de passe.
"""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.errors import DomainError


class SecretsUnavailable(DomainError):
    status_code = 503
    code = "chiffrement_non_configure"


def _fernet() -> Fernet:
    key = get_settings().secrets_key
    if key is None or not key.get_secret_value():
        raise SecretsUnavailable(
            "SECRETS_KEY n'est pas configurée sur le serveur : impossible d'enregistrer ou "
            "d'utiliser des mots de passe de relève (voir le README du backend)."
        )
    try:
        return Fernet(key.get_secret_value().encode())
    except ValueError as exc:
        raise SecretsUnavailable("SECRETS_KEY invalide (clé Fernet attendue)") from exc


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise SecretsUnavailable(
            "Impossible de déchiffrer le mot de passe : SECRETS_KEY a changé. Ressaisissez-le."
        ) from exc
