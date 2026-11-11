"""Règles métier du module auth."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.db import set_db_context
from app.core.errors import Conflict, DomainError, Forbidden, NotFound, Unauthorized
from app.core.security import (
    DUMMY_HASH,
    create_access_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.modules import all_permissions
from app.modules.auth import repository as repo
from app.modules.auth.models import Role, RolePermission, User, UserCompanyRole
from app.modules.auth.schemas import (
    CompanyAccess,
    Me,
    RoleCreate,
    RoleRef,
    UserCreate,
    UserInCompany,
    UserRead,
)

# --- Connexion -------------------------------------------------------------------


def login(db: Session, email: str, password: str) -> str:
    user = repo.get_user_by_email(db, email)
    if user is None:
        verify_password(password, DUMMY_HASH)  # même durée de réponse que pour un vrai compte
        raise Unauthorized("E-mail ou mot de passe incorrect")
    if not verify_password(password, user.password_hash) or not user.is_active:
        # Message identique dans tous les cas : on ne dit pas si le compte existe.
        raise Unauthorized("E-mail ou mot de passe incorrect")

    set_db_context(db, user_id=user.id, company_id=None)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = datetime.now(UTC)
    db.commit()
    return create_access_token(user.id)


def me(db: Session, ctx: RequestContext) -> Me:
    user = repo.get_user(db, ctx.user_id)
    by_company: dict[int, list[RoleRef]] = {}
    for m in repo.memberships(db, ctx.user_id):
        by_company.setdefault(m.company_id, []).append(RoleRef.model_validate(m.role))
    if ctx.is_superuser and ctx.company_id is not None:
        permissions = ["*"]
    else:
        permissions = sorted(ctx.permissions)
    return Me(
        user=UserRead.model_validate(user),
        companies=[CompanyAccess(company_id=c, roles=r) for c, r in by_company.items()],
        current_company_id=ctx.company_id,
        permissions=permissions,
    )


# --- Utilisateurs (dans la société courante) --------------------------------------


def list_users(db: Session, ctx: RequestContext) -> list[UserInCompany]:
    users: dict[int, UserInCompany] = {}
    for user, role in repo.users_in_company(db, ctx.company_id):
        if user.id not in users:
            users[user.id] = UserInCompany(**UserRead.model_validate(user).model_dump(), roles=[])
        users[user.id].roles.append(RoleRef.model_validate(role))
    return list(users.values())


def create_user(db: Session, ctx: RequestContext, data: UserCreate) -> User:
    if repo.get_user_by_email(db, data.email):
        raise Conflict("Un compte existe déjà avec cet e-mail")
    user = User(
        email=data.email,
        full_name=data.full_name,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    db.flush()
    for role_id in data.role_ids:
        _assign(db, ctx, user.id, role_id)
    db.commit()
    return user


def assign_role(db: Session, ctx: RequestContext, user_id: int, role_id: int) -> None:
    if repo.get_user(db, user_id) is None:
        raise NotFound("Utilisateur introuvable")
    _assign(db, ctx, user_id, role_id)
    db.commit()


def _assign(db: Session, ctx: RequestContext, user_id: int, role_id: int) -> None:
    role = repo.get_role(db, role_id)
    if role is None:
        raise NotFound(f"Rôle {role_id} introuvable")
    if role.code == "admin" and not ctx.has("*"):
        # Éviter l'escalade : seul un admin peut nommer un autre admin.
        raise Forbidden("Seul un administrateur peut attribuer le rôle admin")
    if not repo.has_role(db, user_id, ctx.company_id, role_id):
        db.add(UserCompanyRole(user_id=user_id, company_id=ctx.company_id, role_id=role_id))
        db.flush()


def remove_role(db: Session, ctx: RequestContext, user_id: int, role_id: int) -> None:
    if user_id == ctx.user_id:
        role = repo.get_role(db, role_id)
        if role and role.code == "admin":
            raise DomainError("Vous ne pouvez pas retirer votre propre rôle admin")
    if repo.remove_role(db, user_id, ctx.company_id, role_id) == 0:
        raise NotFound("Cette affectation n'existe pas")
    db.commit()


def grant_role(db: Session, *, user_id: int, company_id: int, role_code: str) -> None:
    """Attribue un rôle sans contrôle de droits (usage interne : création de société, CLI)."""
    role = repo.get_role_by_code(db, role_code)
    if role is None:
        raise NotFound(f"Rôle « {role_code} » introuvable")
    if not repo.has_role(db, user_id, company_id, role.id):
        db.add(UserCompanyRole(user_id=user_id, company_id=company_id, role_id=role.id))
        db.flush()


# --- Rôles -------------------------------------------------------------------------


def _validate_permissions(codes: list[str]) -> list[str]:
    catalog = all_permissions()
    modules = {code.split(":", 1)[0] for code in catalog}
    unknown = [
        c
        for c in codes
        if c != "*" and c not in catalog and not (c.endswith(":*") and c[:-2] in modules)
    ]
    if unknown:
        raise DomainError(
            f"Permissions inconnues : {', '.join(unknown)}", code="permission_inconnue"
        )
    return sorted(set(codes))


def list_roles(db: Session) -> list[Role]:
    return repo.list_roles(db)


def create_role(db: Session, data: RoleCreate) -> Role:
    if repo.get_role_by_code(db, data.code):
        raise Conflict(f"Le rôle « {data.code} » existe déjà")
    role = Role(code=data.code, name=data.name, description=data.description)
    role.permissions = [
        RolePermission(permission=p) for p in _validate_permissions(data.permissions)
    ]
    db.add(role)
    db.commit()
    return role


def set_role_permissions(db: Session, role_id: int, codes: list[str]) -> Role:
    role = repo.get_role(db, role_id)
    if role is None:
        raise NotFound("Rôle introuvable")
    if role.is_system:
        raise Forbidden("Un rôle système ne peut pas être modifié")
    wanted = set(_validate_permissions(codes))
    role.permissions = [p for p in role.permissions if p.permission in wanted]
    existing = {p.permission for p in role.permissions}
    role.permissions.extend(RolePermission(permission=c) for c in sorted(wanted - existing))
    db.commit()
    return role
