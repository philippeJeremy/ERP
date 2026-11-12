"""Mot de passe provisoire : changement obligatoire à la première connexion.

Les comptes existants ne sont pas concernés (valeur par défaut : false).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-12 23:20:13.360966
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), server_default="false", nullable=False),
        schema="auth",
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password", schema="auth")
