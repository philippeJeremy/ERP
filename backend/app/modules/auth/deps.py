"""Dépendances FastAPI d'authentification et d'autorisation.

Chaque requête protégée passe par `get_context` :
  1. lit le jeton JWT (en-tête Authorization: Bearer …) → l'utilisateur ;
  2. lit l'en-tête X-Company-Id → la société courante (facultatif) ;
  3. vérifie que l'utilisateur a accès à cette société et charge ses permissions ;
  4. transmet utilisateur + société à PostgreSQL (RLS, audit).
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.db import get_db, set_db_context
from app.core.errors import DomainError, Forbidden, Unauthorized
from app.core.security import InvalidTokenError, decode_access_token
from app.modules.auth import repository as repo

# tokenUrl relatif : Swagger le résout par rapport à sa propre URL (fonctionne derrière /api).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_context(
    token: str = Depends(oauth2_scheme),
    x_company_id: Annotated[int | None, Header(description="Société courante")] = None,
    db: Session = Depends(get_db),
) -> RequestContext:
    try:
        user_id = decode_access_token(token)
    except InvalidTokenError as exc:
        raise Unauthorized("Jeton invalide ou expiré") from exc

    set_db_context(db, user_id=user_id, company_id=x_company_id)

    user = repo.get_user(db, user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Compte inexistant ou désactivé")

    permissions: set[str] = set()
    if x_company_id is not None:
        found = repo.permissions_in_company(db, user_id, x_company_id)
        if found is None and not user.is_superuser:
            raise Forbidden("Vous n'avez pas accès à cette société")
        permissions = found or set()

    return RequestContext(
        user_id=user.id,
        is_superuser=user.is_superuser,
        company_id=x_company_id,
        permissions=frozenset(permissions),
    )


def require(permission: str) -> Callable[..., RequestContext]:
    """Fabrique une dépendance qui exige une société courante ET une permission.

    Usage : `ctx: RequestContext = Depends(require("sales:write"))`
    """

    def dependency(ctx: RequestContext = Depends(get_context)) -> RequestContext:
        if ctx.company_id is None:
            raise DomainError(
                "Choisissez une société (en-tête X-Company-Id)", code="societe_requise"
            )
        if not ctx.has(permission):
            raise Forbidden(f"Permission requise : {permission}")
        return ctx

    return dependency


def require_superuser(ctx: RequestContext = Depends(get_context)) -> RequestContext:
    if not ctx.is_superuser:
        raise Forbidden("Réservé aux super-administrateurs")
    return ctx
