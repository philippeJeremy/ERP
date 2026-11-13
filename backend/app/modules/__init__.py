"""Registre des modules métier.

Ajouter un module = créer son dossier (models, schemas, repository, service, router,
permissions, public) puis ajouter son nom ici. L'ordre compte : un module ne dépend
que de modules placés AVANT lui dans la liste.
"""

from importlib import import_module
from importlib.util import find_spec

from fastapi import APIRouter

MODULES = ["auth", "org", "partners", "catalog", "purchasing"]


def load_models() -> None:
    """Importe tous les modèles pour que SQLAlchemy et Alembic connaissent toutes les tables."""
    for name in MODULES:
        import_module(f"app.modules.{name}.models")


def load_jobs() -> None:
    """Importe les tâches de fond des modules (fichier `jobs.py` facultatif)."""
    for name in MODULES:
        if find_spec(f"app.modules.{name}.jobs") is not None:
            import_module(f"app.modules.{name}.jobs")


def routers() -> list[APIRouter]:
    return [import_module(f"app.modules.{name}.router").router for name in MODULES]


def all_permissions() -> dict[str, str]:
    """Catalogue de toutes les permissions déclarées par les modules (code → libellé)."""
    catalog: dict[str, str] = {}
    for name in MODULES:
        catalog.update(import_module(f"app.modules.{name}.permissions").PERMISSIONS)
    return catalog
