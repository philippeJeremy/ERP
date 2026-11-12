"""Mots de passe (Argon2id) et jetons JWT."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

# Argon2id : l'algorithme recommandé par l'OWASP. Volontairement lent et gourmand en
# mémoire pour rendre les attaques par force brute coûteuses si la base fuit.
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Vrai si les paramètres Argon2 ont été renforcés depuis le hash : on rehashe au login."""
    return _hasher.check_needs_rehash(password_hash)


# Hash factice calculé une fois : au login d'un e-mail inconnu, on vérifie quand même
# un mot de passe pour que la réponse prenne le même temps (pas d'énumération des comptes).
DUMMY_HASH = _hasher.hash("mot-de-passe-factice")


class InvalidTokenError(Exception):
    pass


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), settings.jwt_algorithm)


def decode_access_token(token: str) -> int:
    """Renvoie l'id utilisateur contenu dans le jeton, ou lève InvalidTokenError."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],  # liste fermée : refuse « alg: none »
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    if payload.get("type") != "access":
        raise InvalidTokenError("type de jeton inattendu")
    return int(payload["sub"])


def new_refresh_token() -> str:
    """Jeton aléatoire opaque (256 bits). Ce n'est PAS un JWT : il ne contient rien,
    il sert seulement de clé pour retrouver la session en base."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """On ne stocke que l'empreinte SHA-256 : une fuite de la base ne donne pas de
    jetons utilisables. (Argon2 serait inutilement lent : le jeton est déjà aléatoire.)"""
    return hashlib.sha256(token.encode()).hexdigest()
