"""Règles métier du module auth."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.context import RequestContext
from app.core.db import set_db_context
from app.core.errors import Conflict, DomainError, Forbidden, NotFound, Unauthorized
from app.core.security import (
    DUMMY_HASH,
    create_access_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    new_refresh_token,
    verify_password,
)
from app.modules import all_permissions
from app.modules.auth import repository as repo
from app.modules.auth.models import RefreshToken, Role, RolePermission, User, UserCompanyRole
from app.modules.auth.schemas import (
    CompanyAccess,
    Me,
    PasswordChange,
    ProfileUpdate,
    RoleCreate,
    RoleRef,
    RoleUpdate,
    SessionInfo,
    UserAttach,
    UserCreate,
    UserInCompany,
    UserRead,
    UserUpdate,
)

# --- Connexion -------------------------------------------------------------------


@dataclass(frozen=True)
class AuthTokens:
    """Résultat d'une connexion ou d'un renouvellement : les deux jetons."""

    access_token: str
    refresh_token: str
    session_ends_at: datetime  # fin absolue de la session (durée de vie du cookie)


# Délai pendant lequel un jeton tout juste remplacé peut être présenté sans être
# considéré comme volé : deux onglets qui renouvellent en même temps envoient le même
# cookie. Le second reçoit un refus simple et réessaie avec le nouveau cookie.
ROTATION_GRACE = timedelta(seconds=10)


def login(db: Session, email: str, password: str, *, user_agent: str | None = None) -> AuthTokens:
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
    started = datetime.now(UTC)
    refresh = _issue_refresh_token(
        db, user.id, family_id=uuid.uuid4(), started_at=started, user_agent=user_agent
    )
    db.commit()
    return AuthTokens(create_access_token(user.id), refresh, _session_end(started))


def refresh_session(
    db: Session, raw_token: str | None, *, user_agent: str | None = None
) -> AuthTokens:
    """Échange un refresh token valide contre une nouvelle paire de jetons (rotation)."""
    if not raw_token:
        raise Unauthorized("Session absente")
    now = datetime.now(UTC)
    token = repo.get_refresh_token(db, hash_refresh_token(raw_token), for_update=True)
    if token is None:
        raise Unauthorized("Session inconnue")

    if token.revoked_at is not None:
        if token.revoked_reason == "rotated" and now - token.revoked_at > ROTATION_GRACE:
            # Jeton déjà remplacé, rejoué bien plus tard : vol probable.
            repo.revoke_family(db, token.family_id, reason="reuse", now=now)
            db.commit()
        raise Unauthorized("Session expirée, reconnectez-vous")

    if token.expires_at <= now or _session_end(token.session_started_at) <= now:
        # Inactivité trop longue, ou durée maximale de session atteinte.
        raise Unauthorized("Session expirée, reconnectez-vous")

    user = repo.get_user(db, token.user_id)
    if user is None or not user.is_active:
        repo.revoke_family(db, token.family_id, reason="disabled", now=now)
        db.commit()
        raise Unauthorized("Compte désactivé")

    token.revoked_at = now
    token.revoked_reason = "rotated"
    refresh = _issue_refresh_token(
        db,
        user.id,
        family_id=token.family_id,
        started_at=token.session_started_at,
        user_agent=user_agent,
    )
    db.commit()
    return AuthTokens(create_access_token(user.id), refresh, _session_end(token.session_started_at))


def logout(db: Session, raw_token: str | None) -> None:
    """Révoque la session (toute la famille de jetons). Sans erreur si elle n'existe pas."""
    if not raw_token:
        return
    token = repo.get_refresh_token(db, hash_refresh_token(raw_token))
    if token is not None:
        repo.revoke_family(db, token.family_id, reason="logout", now=datetime.now(UTC))
        db.commit()


def purge_expired_refresh_tokens(db: Session, *, older_than_days: int = 30) -> int:
    """Supprime les sessions expirées depuis longtemps (tâche planifiée du worker)."""
    count = repo.delete_expired_refresh_tokens(
        db, before=datetime.now(UTC) - timedelta(days=older_than_days)
    )
    db.commit()
    return count


def _session_end(started_at: datetime) -> datetime:
    return started_at + timedelta(hours=get_settings().session_max_hours)


def _issue_refresh_token(
    db: Session,
    user_id: int,
    *,
    family_id: uuid.UUID,
    started_at: datetime,
    user_agent: str | None,
) -> str:
    now = datetime.now(UTC)
    idle_limit = now + timedelta(minutes=get_settings().session_idle_minutes)
    raw = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user_id,
            family_id=family_id,
            token_hash=hash_refresh_token(raw),
            session_started_at=started_at,
            expires_at=min(idle_limit, _session_end(started_at)),
            user_agent=(user_agent or "")[:255] or None,
        )
    )
    db.flush()
    return raw


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
        session_idle_minutes=get_settings().session_idle_minutes,
    )


# --- Mon profil -------------------------------------------------------------------


def update_profile(db: Session, ctx: RequestContext, data: ProfileUpdate) -> User:
    user = repo.get_user(db, ctx.user_id)
    user.full_name = data.full_name
    db.commit()
    return user


def _current_family(db: Session, raw_token: str | None) -> uuid.UUID | None:
    if not raw_token:
        return None
    token = repo.get_refresh_token(db, hash_refresh_token(raw_token))
    return token.family_id if token is not None else None


def change_password(
    db: Session, ctx: RequestContext, data: PasswordChange, raw_token: str | None
) -> None:
    """Change le mot de passe et ferme toutes les AUTRES sessions.

    Si le mot de passe a fuité, les sessions ouvertes par l'attaquant tombent ;
    celle de ce navigateur reste ouverte.
    """
    user = repo.get_user(db, ctx.user_id)
    if not verify_password(data.current_password, user.password_hash):
        raise DomainError("Mot de passe actuel incorrect", code="mot_de_passe_incorrect")
    if data.new_password == data.current_password:
        raise DomainError("Le nouveau mot de passe doit être différent de l'actuel")
    user.password_hash = hash_password(data.new_password)
    user.must_change_password = False
    repo.revoke_user_families(
        db, user.id, reason="logout", now=datetime.now(UTC), keep=_current_family(db, raw_token)
    )
    db.commit()


def list_sessions(db: Session, ctx: RequestContext, raw_token: str | None) -> list[SessionInfo]:
    current = _current_family(db, raw_token)
    return [
        SessionInfo(
            id=t.family_id,
            started_at=t.session_started_at,
            last_used_at=t.created_at,
            expires_at=t.expires_at,
            user_agent=t.user_agent,
            current=t.family_id == current,
        )
        for t in repo.active_sessions(db, ctx.user_id, now=datetime.now(UTC))
    ]


def revoke_session(db: Session, ctx: RequestContext, family_id: uuid.UUID) -> None:
    # Le filtre sur user_id empêche de fermer la session de quelqu'un d'autre.
    count = repo.revoke_user_families(
        db, ctx.user_id, reason="logout", now=datetime.now(UTC), only=family_id
    )
    if count == 0:
        raise NotFound("Session introuvable")
    db.commit()


def revoke_other_sessions(db: Session, ctx: RequestContext, raw_token: str | None) -> int:
    count = repo.revoke_user_families(
        db, ctx.user_id, reason="logout", now=datetime.now(UTC), keep=_current_family(db, raw_token)
    )
    db.commit()
    return count


# --- Utilisateurs (dans la société courante) --------------------------------------
#
# Règles anti-escalade (un administrateur ne doit pas pouvoir se donner, ou prendre à
# quelqu'un, plus de droits qu'il n'en a) :
#   1. on ne peut attribuer ou retirer qu'un rôle dont on possède TOUTES les permissions ;
#   2. on ne peut pas modifier ses propres rôles ni désactiver son propre compte ;
#   3. on ne peut modifier l'identité d'un compte (nom, e-mail, mot de passe, activation)
#      que s'il n'a pas plus de droits que soi et n'appartient qu'à la société courante.
#      Sinon, réinitialiser son mot de passe reviendrait à prendre la main sur ses
#      accès ailleurs. Un super-administrateur n'a pas ces limites.


def _can_grant(ctx: RequestContext, role: Role) -> bool:
    return all(ctx.has(permission) for permission in role.permission_codes)


def _user_view(db: Session, ctx: RequestContext, user: User) -> UserInCompany:
    return UserInCompany(
        **UserRead.model_validate(user).model_dump(),
        roles=[
            RoleRef.model_validate(r) for r in repo.roles_in_company(db, user.id, ctx.company_id)
        ],
        multi_company=repo.company_counts(db, [user.id]).get(user.id, 0) > 1,
    )


def _get_member(db: Session, ctx: RequestContext, user_id: int) -> User:
    """L'utilisateur, s'il a accès à la société courante (sinon 404, même s'il existe)."""
    user = repo.get_user(db, user_id)
    if user is None or (
        not ctx.is_superuser and ctx.company_id not in repo.company_ids_of(db, user_id)
    ):
        raise NotFound("Utilisateur introuvable")
    return user


def _ensure_can_manage_account(db: Session, ctx: RequestContext, user: User) -> None:
    if ctx.is_superuser:
        return
    if user.is_superuser:
        raise Forbidden("Seul un super-administrateur peut modifier ce compte")
    if repo.company_ids_of(db, user.id) - {ctx.company_id}:
        raise Forbidden(
            "Ce compte a accès à d'autres sociétés : seul un super-administrateur peut "
            "le modifier. Vous pouvez gérer ses rôles dans cette société."
        )
    if not all(_can_grant(ctx, r) for r in repo.roles_in_company(db, user.id, ctx.company_id)):
        raise Forbidden("Ce compte a plus de droits que vous : vous ne pouvez pas le modifier")


def list_users(db: Session, ctx: RequestContext) -> list[UserInCompany]:
    users: dict[int, UserInCompany] = {}
    for user, role in repo.users_in_company(db, ctx.company_id):
        if user.id not in users:
            users[user.id] = UserInCompany(**UserRead.model_validate(user).model_dump(), roles=[])
        users[user.id].roles.append(RoleRef.model_validate(role))
    counts = repo.company_counts(db, list(users))
    for user_id, view in users.items():
        view.multi_company = counts.get(user_id, 0) > 1
    return list(users.values())


def get_user(db: Session, ctx: RequestContext, user_id: int) -> UserInCompany:
    return _user_view(db, ctx, _get_member(db, ctx, user_id))


def create_user(db: Session, ctx: RequestContext, data: UserCreate) -> UserInCompany:
    if not data.role_ids:
        # Sans rôle, le compte n'aurait accès à aucune société et n'apparaîtrait nulle part.
        raise DomainError("Attribuez au moins un rôle au nouvel utilisateur", code="role_requis")
    if repo.get_user_by_email(db, data.email):
        raise Conflict("Un compte existe déjà avec cet e-mail", code="compte_existant")
    user = User(
        email=data.email,
        full_name=data.full_name,
        password_hash=hash_password(data.password),
        must_change_password=True,  # le mot de passe choisi par l'administrateur est provisoire
    )
    db.add(user)
    db.flush()
    for role_id in set(data.role_ids):
        _assign(db, ctx, user.id, role_id)
    db.commit()
    return _user_view(db, ctx, user)


def attach_user(db: Session, ctx: RequestContext, data: UserAttach) -> UserInCompany:
    """Donne accès à la société courante à un compte existant (créé dans une autre société)."""
    if not data.role_ids:
        raise DomainError("Attribuez au moins un rôle", code="role_requis")
    user = repo.get_user_by_email(db, data.email)
    if user is None:
        raise NotFound("Aucun compte avec cet e-mail")
    if ctx.company_id in repo.company_ids_of(db, user.id):
        raise Conflict("Ce compte a déjà accès à cette société")
    for role_id in set(data.role_ids):
        _assign(db, ctx, user.id, role_id)
    db.commit()
    return _user_view(db, ctx, user)


def update_user(db: Session, ctx: RequestContext, user_id: int, data: UserUpdate) -> UserInCompany:
    user = _get_member(db, ctx, user_id)
    _ensure_can_manage_account(db, ctx, user)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)

    if "email" in changes and changes["email"].lower() != user.email.lower():
        if repo.get_user_by_email(db, changes["email"]):
            raise Conflict("Un compte existe déjà avec cet e-mail", code="compte_existant")
        user.email = changes["email"]
    if "full_name" in changes:
        user.full_name = changes["full_name"]
    if "is_active" in changes and changes["is_active"] != user.is_active:
        if user.id == ctx.user_id:
            raise DomainError("Vous ne pouvez pas désactiver votre propre compte")
        user.is_active = changes["is_active"]
        if not user.is_active:
            # Compte désactivé : ses sessions ouvertes sont fermées tout de suite.
            repo.revoke_user_families(db, user.id, reason="disabled", now=datetime.now(UTC))
    db.commit()
    return _user_view(db, ctx, user)


def reset_password(db: Session, ctx: RequestContext, user_id: int, new_password: str) -> None:
    """Un administrateur définit un nouveau mot de passe ; toutes les sessions du compte tombent."""
    user = _get_member(db, ctx, user_id)
    if user.id == ctx.user_id:
        raise DomainError("Pour votre propre mot de passe, utilisez votre page de profil")
    _ensure_can_manage_account(db, ctx, user)
    user.password_hash = hash_password(new_password)
    user.must_change_password = True
    repo.revoke_user_families(db, user.id, reason="logout", now=datetime.now(UTC))
    db.commit()


def set_user_roles(
    db: Session, ctx: RequestContext, user_id: int, role_ids: list[int]
) -> UserInCompany:
    """Remplace ses rôles dans la société courante (liste vide = retirer son accès)."""
    user = _get_member(db, ctx, user_id)
    if user.id == ctx.user_id:
        raise DomainError("Vous ne pouvez pas modifier vos propres rôles")
    current = {r.id: r for r in repo.roles_in_company(db, user.id, ctx.company_id)}
    wanted = set(role_ids)

    for role_id in wanted - set(current):
        _assign(db, ctx, user.id, role_id)
    for role_id in set(current) - wanted:
        if not _can_grant(ctx, current[role_id]):
            raise Forbidden(f"Vous ne pouvez pas retirer le rôle « {current[role_id].name} »")
        repo.remove_role(db, user.id, ctx.company_id, role_id)
    db.commit()
    return _user_view(db, ctx, user)


def assign_role(db: Session, ctx: RequestContext, user_id: int, role_id: int) -> None:
    if repo.get_user(db, user_id) is None:
        raise NotFound("Utilisateur introuvable")
    _assign(db, ctx, user_id, role_id)
    db.commit()


def _assign(db: Session, ctx: RequestContext, user_id: int, role_id: int) -> None:
    role = repo.get_role(db, role_id)
    if role is None:
        raise NotFound(f"Rôle {role_id} introuvable")
    if not _can_grant(ctx, role):
        # Éviter l'escalade : on ne donne pas plus de droits qu'on n'en a.
        raise Forbidden(
            f"Vous ne pouvez pas attribuer le rôle « {role.name} » : il donne des droits "
            "que vous n'avez pas"
        )
    if not repo.has_role(db, user_id, ctx.company_id, role_id):
        db.add(UserCompanyRole(user_id=user_id, company_id=ctx.company_id, role_id=role_id))
        db.flush()


def remove_role(db: Session, ctx: RequestContext, user_id: int, role_id: int) -> None:
    if user_id == ctx.user_id:
        raise DomainError("Vous ne pouvez pas modifier vos propres rôles")
    role = repo.get_role(db, role_id)
    if role is not None and not _can_grant(ctx, role):
        raise Forbidden(f"Vous ne pouvez pas retirer le rôle « {role.name} »")
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
    roles = repo.list_roles(db)
    counts = repo.role_user_counts(db)
    for role in roles:
        role.user_count = counts.get(role.id, 0)  # attribut lu par le schéma RoleRead
    return roles


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


def _editable_role(db: Session, role_id: int) -> Role:
    role = repo.get_role(db, role_id)
    if role is None:
        raise NotFound("Rôle introuvable")
    if role.is_system:
        raise Forbidden("Un rôle système ne peut pas être modifié")
    return role


def _set_permissions(role: Role, codes: list[str]) -> None:
    wanted = set(_validate_permissions(codes))
    role.permissions = [p for p in role.permissions if p.permission in wanted]
    existing = {p.permission for p in role.permissions}
    role.permissions.extend(RolePermission(permission=c) for c in sorted(wanted - existing))


def set_role_permissions(db: Session, role_id: int, codes: list[str]) -> Role:
    role = _editable_role(db, role_id)
    _set_permissions(role, codes)
    db.commit()
    return role


def update_role(db: Session, role_id: int, data: RoleUpdate) -> Role:
    role = _editable_role(db, role_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("name"):
        role.name = changes["name"]
    if "description" in changes:
        role.description = changes["description"] or None
    if changes.get("permissions") is not None:
        _set_permissions(role, changes["permissions"])
    db.commit()
    role.user_count = repo.role_user_counts(db).get(role.id, 0)
    return role


def delete_role(db: Session, role_id: int) -> None:
    role = _editable_role(db, role_id)
    count = repo.role_user_counts(db).get(role.id, 0)
    if count:
        # On ne retire pas silencieusement des droits à des utilisateurs.
        raise Conflict(
            f"Ce rôle est attribué à {count} utilisateur(s) : retirez-le-leur d'abord",
            code="role_utilise",
        )
    db.delete(role)
    db.commit()
