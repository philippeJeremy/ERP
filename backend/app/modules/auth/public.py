"""Interface publique du module auth : ce que les autres modules ont le droit d'importer.

Dans un router :   ctx: RequestContext = Depends(require("sales:write"))
"""

from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.modules.auth.deps import add_company_guard, get_context, require, require_superuser
from app.modules.auth.repository import company_ids_of, revoke_company_access
from app.modules.auth.service import (
    grant_role,
    purge_expired_refresh_tokens,
    user_company_access,
)


def user_full_name(db: Session, user_id: int | None) -> str | None:
    """Nom affiché d'un utilisateur (signature des mails…)."""
    from app.modules.auth.models import User

    user = db.get(User, user_id) if user_id else None
    return user.full_name if user else None


__all__ = [
    "RequestContext",
    "user_full_name",
    "add_company_guard",
    "company_ids_of",
    "get_context",
    "grant_role",
    "purge_expired_refresh_tokens",
    "require",
    "require_superuser",
    "revoke_company_access",
    "user_company_access",
]
