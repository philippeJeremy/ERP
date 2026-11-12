"""Configuration de l'application.

Tout vient des variables d'environnement (règle « compatible Kubernetes ») :
aucune valeur sensible dans le code, et la même image tourne en dev, test et prod.
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    environment: Literal["dev", "test", "prod"] = "dev"
    app_version: str = "dev"  # injectée dans l'image au build (tag Git)
    log_level: str = "INFO"

    # Connexion de l'API : rôle PostgreSQL `erp_app` (lecture/écriture des données, pas de DDL).
    database_url: str
    # Connexion des migrations : rôle `erp_owner` (propriétaire des tables).
    # Seul le job `migrate` en a besoin.
    migration_database_url: str | None = None

    redis_url: str = "redis://redis:6379/0"

    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    # Jeton d'accès court : s'il fuit, il ne sert pas longtemps. Le frontend le
    # renouvelle tout seul grâce au refresh token.
    access_token_minutes: int = 15

    # Refresh token : stocké dans un cookie httpOnly (JavaScript ne peut pas le lire,
    # donc une faille XSS ne permet pas de le voler).
    refresh_token_days: int = 7
    refresh_cookie_name: str = "erp_refresh"
    # Chemin vu par le NAVIGATEUR (avant que Caddy retire /api) : le cookie n'est
    # envoyé qu'aux routes /api/auth/*, jamais au reste de l'API.
    refresh_cookie_path: str = "/api/auth"
    cookie_secure: bool = True  # HTTPS uniquement (localhost est toléré par les navigateurs)

    # Préfixe sous lequel Caddy expose l'API (ex. « /api ») : sert à Swagger pour
    # générer les bonnes URL quand le proxy retire ce préfixe.
    root_path: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # valeurs lues dans l'environnement
