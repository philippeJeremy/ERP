"""Durée des sessions : expiration après inactivité + durée maximale.

Les sessions ouvertes avant cette version avaient une durée de 7 jours renouvelée
à l'infini : elles sont toutes supprimées, chacun se reconnecte une fois.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-12 16:11:58.590675
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Vider la table AVANT d'ajouter une colonne obligatoire (sinon : pas de valeur
    # pour les lignes existantes).
    op.execute("DELETE FROM auth.refresh_tokens")
    op.add_column(
        "refresh_tokens",
        sa.Column("session_started_at", sa.DateTime(timezone=True), nullable=False),
        schema="auth",
    )


def downgrade() -> None:
    op.drop_column("refresh_tokens", "session_started_at", schema="auth")
