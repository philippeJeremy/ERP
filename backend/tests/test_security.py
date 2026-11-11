from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_puis_verification():
    h = hash_password("un-mot-de-passe-solide")
    assert h.startswith("$argon2id$")
    assert verify_password("un-mot-de-passe-solide", h)
    assert not verify_password("mauvais", h)


def test_hash_invalide_ne_plante_pas():
    assert not verify_password("x", "pas-un-hash")


def test_jeton_aller_retour():
    assert decode_access_token(create_access_token(42)) == 42


def test_jeton_expire_refuse():
    s = get_settings()
    past = datetime.now(UTC) - timedelta(minutes=5)
    token = jwt.encode(
        {"sub": "1", "type": "access", "exp": past}, s.jwt_secret.get_secret_value(), "HS256"
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_jeton_signe_avec_autre_cle_refuse():
    token = jwt.encode(
        {"sub": "1", "type": "access", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        "une-autre-cle-tres-longue-0123456789abcdef",
        "HS256",
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_jeton_alg_none_refuse():
    token = jwt.encode({"sub": "1", "type": "access"}, None, algorithm="none")
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)
