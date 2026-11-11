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
    log_level: str = "INFO"

    # Connexion de l'API : rôle PostgreSQL `erp_app` (lecture/écriture des données, pas de DDL).
    database_url: str
    # Connexion des migrations : rôle `erp_owner` (propriétaire des tables).
    # Seul le job `migrate` en a besoin.
    migration_database_url: str | None = None

    redis_url: str = "redis://redis:6379/0"

    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30

    # Préfixe sous lequel Caddy expose l'API (ex. « /api ») : sert à Swagger pour
    # générer les bonnes URL quand le proxy retire ce préfixe.
    root_path: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # valeurs lues dans l'environnement
