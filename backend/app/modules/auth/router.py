from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.db import get_db
from app.modules import all_permissions
from app.modules.auth import service
from app.modules.auth.deps import get_context, require, require_superuser
from app.modules.auth.schemas import (
    Me,
    PermissionInfo,
    RoleAssignment,
    RoleCreate,
    RolePermissionsUpdate,
    RoleRead,
    Token,
    UserCreate,
    UserInCompany,
    UserRead,
)

router = APIRouter(prefix="/auth", tags=["Authentification et droits"])


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Connexion. Format formulaire OAuth2 (champ `username` = e-mail) : c'est ce qui
    fait fonctionner le bouton « Authorize » de la documentation Swagger."""
    return Token(access_token=service.login(db, form.username, form.password))


@router.get("/me", response_model=Me)
def me(db: Session = Depends(get_db), ctx: RequestContext = Depends(get_context)):
    return service.me(db, ctx)


@router.get("/permissions", response_model=list[PermissionInfo])
def permissions(_=Depends(get_context)):
    """Catalogue des permissions déclarées par les modules (pour l'écran des rôles)."""
    return [PermissionInfo(code=c, label=label) for c, label in sorted(all_permissions().items())]


# --- Utilisateurs de la société courante ------------------------------------------


@router.get("/users", response_model=list[UserInCompany])
def list_users(db: Session = Depends(get_db), ctx: RequestContext = Depends(require("auth:read"))):
    return service.list_users(db, ctx)


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(require("auth:manage")),
):
    return service.create_user(db, ctx, data)


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
