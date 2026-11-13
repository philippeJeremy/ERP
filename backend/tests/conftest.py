"""Configuration des tests.

- Tests unitaires : aucune base nécessaire.
- Tests marqués `db` : besoin d'un PostgreSQL migré (alembic upgrade head) :
    TEST_DATABASE_URL            connexion erp_app
    TEST_MIGRATION_DATABASE_URL  connexion erp_owner (vérifications « vue d'admin »)
  Sans ces variables, ils sont ignorés.
"""

import os

import pytest

# À définir AVANT d'importer l'application (la configuration est lue à l'import).
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://erp_app:x@127.0.0.1:1/absent"),
)
os.environ.setdefault("JWT_SECRET", "secret-de-test-uniquement-0123456789abcdef")
os.environ.setdefault("ENVIRONMENT", "test")
# Tâches de fond exécutées tout de suite, sans worker ni Redis.
os.environ.setdefault("JOBS_INLINE", "true")
os.environ.setdefault("SMTP_ALLOW_PRIVATE_HOSTS", "true")  # serveur SMTP de test local

HAS_DB = bool(os.environ.get("TEST_DATABASE_URL"))


def pytest_collection_modifyitems(config, items):
    if HAS_DB:
        return
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL non défini")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)
