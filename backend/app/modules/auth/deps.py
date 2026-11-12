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


# Contrôles supplémentaires sur la société courante, enregistrés par d'autres modules
# (le module org refuse une société désactivée). `auth` ne dépend d'aucun module :
# ce sont eux qui viennent se brancher ici, pas l'inverse.
CompanyGuard = Callable[[Session, int], None]
_company_guards: list[CompanyGuard] = []


def add_company_guard(guard: CompanyGuard) -> None:
    if guard not in _company_guards:
        _company_guards.append(guard)


def _build_context(
    token: str, x_company_id: int | None, db: Session, *, allow_password_pending: bool
) -> RequestContext:
    try:
        user_id = decode_access_token(token)
    except InvalidTokenError as exc:
        raise Unauthorized("Jeton invalide ou expiré") from exc

    set_db_context(db, user_id=user_id, company_id=x_company_id)

    user = repo.get_user(db, user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Compte inexistant ou désactivé")
    if user.must_change_password and not allow_password_pending:
        # Mot de passe provisoire : tant qu'il n'est pas changé, l'API ne répond qu'aux
        # routes nécessaires pour le changer. Le frontend masque le reste, mais c'est
        # ICI que la règle est réellement appliquée.
        raise Forbidden(
            "Vous devez d'abord choisir un nouveau mot de passe", code="mot_de_passe_a_changer"
        )

    permissions: set[str] = set()
    if x_company_id is not None:
        found = repo.permissions_in_company(db, user_id, x_company_id)
        if found is None and not user.is_superuser:
            raise Forbidden("Vous n'avez pas accès à cette société")
        if not user.is_superuser:
            for guard in _company_guards:
                guard(db, x_company_id)
        permissions = found or set()

    return RequestContext(
        user_id=user.id,
        is_superuser=user.is_superuser,
        company_id=x_company_id,
        permissions=frozenset(permissions),
    )


def get_context(
    token: str = Depends(oauth2_scheme),
    x_company_id: Annotated[int | None, Header(description="Société courante")] = None,
    db: Session = Depends(get_db),
) -> RequestContext:
    return _build_context(token, x_company_id, db, allow_password_pending=False)


def get_context_password_pending(
    token: str = Depends(oauth2_scheme),
    x_company_id: Annotated[int | None, Header(description="Société courante")] = None,
    db: Session = Depends(get_db),
) -> RequestContext:
    """Comme get_context, mais accepte un compte dont le mot de passe reste à changer.
    Réservé à GET /auth/me et POST /auth/me/password."""
    return _build_context(token, x_company_id, db, allow_password_pending=True)


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
