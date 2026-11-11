"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}
from app.shared.migrations import enable_audit, enable_company_rls  # noqa: F401

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}
    # Pour chaque nouvelle table métier, ne pas oublier :
    #   enable_company_rls("schema.table")            # ou shared=True si company_id peut être NULL
    #   enable_audit("schema.table")


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
