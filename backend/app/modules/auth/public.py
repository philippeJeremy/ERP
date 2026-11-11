"""Interface publique du module auth : ce que les autres modules ont le droit d'importer.

Dans un router :   ctx: RequestContext = Depends(require("sales:write"))
"""

from app.core.context import RequestContext
from app.modules.auth.deps import get_context, require, require_superuser
from app.modules.auth.repository import company_ids_of
from app.modules.auth.service import grant_role

__all__ = [
    "RequestContext",
    "company_ids_of",
    "get_context",
    "grant_role",
    "require",
    "require_superuser",
]
