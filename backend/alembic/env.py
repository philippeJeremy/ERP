"""Exécution des migrations Alembic (rôle PostgreSQL erp_owner)."""

import os

from sqlalchemy import create_engine, pool

from alembic import context
from app import modules
from app.shared.models import Base

modules.load_models()
target_metadata = Base.metadata

# Schémas comparés par l'autogénération : ceux des modèles. Les autres (public, et
# `audit`, géré à la main dans les migrations) sont ignorés.
MANAGED_SCHEMAS = {t.schema for t in target_metadata.tables.values()}


def include_name(name, type_, parent_names):
    if type_ == "schema":
        return name in MANAGED_SCHEMAS
    return True


def database_url() -> str:
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        raise RuntimeError("Variable MIGRATION_DATABASE_URL absente (connexion erp_owner)")
    return url


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql` : génère le SQL sans se connecter (pour relecture)."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,  # comparer tous les schémas, pas seulement public
            include_name=include_name,
            compare_type=True,  # détecter aussi les changements de type de colonne
            version_table_schema="public",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
