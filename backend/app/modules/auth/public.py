"""Interface publique du module auth : ce que les autres modules ont le droit d'importer.

Dans un router :   ctx: RequestContext = Depends(require("sales:write"))
"""

from app.core.context import RequestContext
from app.modules.auth.deps import add_company_guard, get_context, require, require_superuser
from app.modules.auth.repository import company_ids_of, revoke_company_access
from app.modules.auth.service import (
    grant_role,
    purge_expired_refresh_tokens,
    user_company_access,
)

__all__ = [
    "RequestContext",
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
