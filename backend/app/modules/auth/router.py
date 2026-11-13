import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.context import RequestContext
from app.core.db import get_db
from app.modules import all_permissions
from app.modules.auth import service
from app.modules.auth.deps import (
    get_context,
    get_context_password_pending,
    require,
    require_superuser,
)
from app.modules.auth.schemas import (
    Me,
    PasswordChange,
    PasswordReset,
    PermissionInfo,
    ProfileUpdate,
    RoleAssignment,
    RoleCreate,
    RolePermissionsUpdate,
    RoleRead,
    RoleUpdate,
    SessionInfo,
    Token,
    UserAttach,
    UserCreate,
    UserInCompany,
    UserRead,
    UserRolesUpdate,
    UserUpdate,
)

router = APIRouter(prefix="/auth", tags=["Authentification et droits"])


def _set_refresh_cookie(response: Response, tokens: service.AuthTokens) -> None:
    s = get_settings()
    # Le navigateur supprime le cookie à la fin absolue de la session. (L'inactivité,
    # elle, est contrôlée par l'API : expires_at du jeton en base.)
    remaining = tokens.session_ends_at - datetime.now(UTC)
    response.set_cookie(
        key=s.refresh_cookie_name,
        value=tokens.refresh_token,
        max_age=max(int(remaining.total_seconds()), 0),
        path=s.refresh_cookie_path,
        httponly=True,  # invisible pour JavaScript
        secure=s.cookie_secure,  # jamais envoyé en HTTP clair
        samesite="strict",  # jamais envoyé depuis un autre site (protection CSRF)
    )


def _clear_refresh_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(
        key=s.refresh_cookie_name,
        path=s.refresh_cookie_path,
        httponly=True,
        secure=s.cookie_secure,
        samesite="strict",
    )


RefreshCookie = Annotated[str | None, Cookie(alias=get_settings().refresh_cookie_name)]


@router.post("/login", response_model=Token)
def login(
    request: Request,
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Connexion. Format formulaire OAuth2 (champ `username` = e-mail) : c'est ce qui
    fait fonctionner le bouton « Authorize » de la documentation Swagger.

    Renvoie le jeton d'accès (courte durée) dans la réponse, et pose le refresh token
    dans un cookie httpOnly."""
    tokens = service.login(
        db, form.username, form.password, user_agent=request.headers.get("user-agent")
    )
    _set_refresh_cookie(response, tokens)
    return Token(access_token=tokens.access_token)


@router.post("/refresh", response_model=Token)
def refresh(
    request: Request,
    response: Response,
    refresh_token: RefreshCookie = None,
    db: Session = Depends(get_db),
):
    """Nouveau jeton d'accès à partir du cookie de session (appelé automatiquement par
    le frontend au chargement de la page et quand le jeton d'accès expire)."""
    tokens = service.refresh_session(
        db, refresh_token, user_agent=request.headers.get("user-agent")
    )
    _set_refresh_cookie(response, tokens)
    return Token(access_token=tokens.access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, refresh_token: RefreshCookie = None, db: Session = Depends(get_db)):
    service.logout(db, refresh_token)
    _clear_refresh_cookie(response)


@router.get("/me", response_model=Me)
def me(db: Session = Depends(get_db), ctx: RequestContext = Depends(get_context_password_pending)):
    return service.me(db, ctx)


# --- Mon profil (aucune société requise) ----------------------------------------
# Ces routes sont sous /auth : le navigateur y envoie le cookie de session, ce qui
# permet de reconnaître « la session de ce navigateur ».


@router.patch("/me", response_model=UserRead)
def update_profile(
    data: ProfileUpdate, db: Session = Depends(get_db), ctx: RequestContext = Depends(get_context)
):
    return service.update_profile(db, ctx, data)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    data: PasswordChange,
    refresh_token: RefreshCookie = None,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_context_password_pending),
):
    """Change le mot de passe ; les autres sessions de l'utilisateur sont fermées."""
    service.change_password(db, ctx, data, refresh_token)


@router.get("/me/sessions", response_model=list[SessionInfo])
def list_sessions(
    refresh_token: RefreshCookie = None,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_context),
):
    return service.list_sessions(db, ctx, refresh_token)


@router.post("/me/sessions/revoke-others", status_code=status.HTTP_204_NO_CONTENT)
def revoke_other_sessions(
    refresh_token: RefreshCookie = None,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_context),
):
    service.revoke_other_sessions(db, ctx, refresh_token)


@router.delete("/me/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_id: uuid.UUID, db: Session = Depends(get_db), ctx: RequestContext = Depends(get_context)
):
    service.revoke_session(db, ctx, session_id)


@router.get("/permissions", response_model=list[PermissionInfo])
def permissions(_=Depends(get_context)):
    """Catalogue des permissions déclarées par les modules (pour l'écran des rôles)."""
    return [PermissionInfo(code=c, label=label) for c, label in sorted(all_permissions().items())]


# --- Utilisateurs de la société courante ------------------------------------------


@router.get("/users", response_model=list[UserInCompany])
def list_users(db: Session = Depends(get_db), ctx: RequestContext = Depends(require("auth:read"))):
    return service.list_users(db, ctx)


@router.post("/users", response_model=UserInCompany, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(require("auth:manage")),
):
    return service.create_user(db, ctx, data)


@router.post("/users/attach", response_model=UserInCompany, status_code=status.HTTP_201_CREATED)
def attach_user(
    data: UserAttach,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(require("auth:manage")),
):
    """Donne accès à la société courante à un compte existant."""
    return service.attach_user(db, ctx, data)


@router.get("/users/{user_id}", response_model=UserInCompany)
def get_user(
    user_id: int, db: Session = Depends(get_db), ctx: RequestContext = Depends(require("auth:read"))
):
    return service.get_user(db, ctx, user_id)


@router.patch("/users/{user_id}", response_model=UserInCompany)
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(require("auth:manage")),
):
    return service.update_user(db, ctx, user_id, data)


@router.post("/users/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: int,
    data: PasswordReset,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(require("auth:manage")),
):
    """Réinitialise le mot de passe d'un utilisateur et ferme toutes ses sessions."""
    service.reset_password(db, ctx, user_id, data.new_password)


@router.put("/users/{user_id}/roles", response_model=UserInCompany)
def set_user_roles(
    user_id: int,
    data: UserRolesUpdate,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(require("auth:manage")),
):
    """Remplace les rôles de l'utilisateur dans la société courante."""
    return service.set_user_roles(db, ctx, user_id, data.role_ids)


@router.put("/users/{user_id}/companies/{company_id}/roles", response_model=UserInCompany)
def set_roles_in_company(
    user_id: int,
    company_id: int,
    data: UserRolesUpdate,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_context),
):
    """Donne, modifie ou retire (liste vide) l'accès de l'utilisateur à une société.

    Le droit auth:manage est vérifié DANS la société visée (pas la société courante).
    """
    return service.set_roles_in_company(db, ctx, user_id, company_id, data.role_ids)


@router.post("/users/{user_id}/roles", status_code=status.HTTP_204_NO_CONTENT)
def assign_role(
    user_id: int,
    data: RoleAssignment,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(require("auth:manage")),
):
    """Donne un rôle à l'utilisateur dans la société courante."""
    service.assign_role(db, ctx, user_id, data.role_id)


@router.delete("/users/{user_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_role(
    user_id: int,
    role_id: int,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(require("auth:manage")),
):
    service.remove_role(db, ctx, user_id, role_id)


# --- Rôles (communs à tout le groupe : réservés aux super-administrateurs) --------


@router.get("/roles", response_model=list[RoleRead])
def list_roles(db: Session = Depends(get_db), _=Depends(get_context)):
    return service.list_roles(db)


@router.post("/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
def create_role(data: RoleCreate, db: Session = Depends(get_db), _=Depends(require_superuser)):
    return service.create_role(db, data)


@router.put("/roles/{role_id}/permissions", response_model=RoleRead)
def set_role_permissions(
    role_id: int,
    data: RolePermissionsUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_superuser),
):
    return service.set_role_permissions(db, role_id, data.permissions)


@router.patch("/roles/{role_id}", response_model=RoleRead)
def update_role(
    role_id: int, data: RoleUpdate, db: Session = Depends(get_db), _=Depends(require_superuser)
):
    return service.update_role(db, role_id, data)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(role_id: int, db: Session = Depends(get_db), _=Depends(require_superuser)):
    service.delete_role(db, role_id)
