import uuid
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.modules.auth.models import RefreshToken, Role, RolePermission, User, UserCompanyRole


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email.lower()))


def get_role(db: Session, role_id: int) -> Role | None:
    return db.get(Role, role_id)


def get_role_by_code(db: Session, code: str) -> Role | None:
    return db.scalar(select(Role).where(Role.code == code))


def list_roles(db: Session) -> list[Role]:
    return list(db.scalars(select(Role).order_by(Role.name)))


def memberships(db: Session, user_id: int) -> list[UserCompanyRole]:
    query = (
        select(UserCompanyRole)
        .where(UserCompanyRole.user_id == user_id)
        .order_by(UserCompanyRole.company_id)
    )
    return list(db.scalars(query))


def company_ids_of(db: Session, user_id: int) -> set[int]:
    query = select(UserCompanyRole.company_id).where(UserCompanyRole.user_id == user_id)
    return set(db.scalars(query))


def permissions_in_company(db: Session, user_id: int, company_id: int) -> set[str] | None:
    """Permissions de l'utilisateur dans la société, ou None s'il n'y a aucun accès."""
    query = (
        select(UserCompanyRole.role_id, RolePermission.permission)
        .outerjoin(RolePermission, RolePermission.role_id == UserCompanyRole.role_id)
        .where(UserCompanyRole.user_id == user_id, UserCompanyRole.company_id == company_id)
    )
    rows = db.execute(query).all()
    if not rows:
        return None
    return {permission for _, permission in rows if permission is not None}


def users_in_company(db: Session, company_id: int) -> list[tuple[User, Role]]:
    query = (
        select(User, Role)
        .join(UserCompanyRole, UserCompanyRole.user_id == User.id)
        .join(Role, Role.id == UserCompanyRole.role_id)
        .where(UserCompanyRole.company_id == company_id)
        .order_by(User.full_name, Role.name)
    )
    return [(user, role) for user, role in db.execute(query).all()]


def has_role(db: Session, user_id: int, company_id: int, role_id: int) -> bool:
    return db.get(UserCompanyRole, (user_id, company_id, role_id)) is not None


def remove_role(db: Session, user_id: int, company_id: int, role_id: int) -> int:
    result = db.execute(
        delete(UserCompanyRole).where(
            UserCompanyRole.user_id == user_id,
            UserCompanyRole.company_id == company_id,
            UserCompanyRole.role_id == role_id,
        )
    )
    return result.rowcount


# --- Sessions (refresh tokens) --------------------------------------------------


def get_refresh_token(
    db: Session, token_hash: str, *, for_update: bool = False
) -> RefreshToken | None:
    query = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    if for_update:
        # Deux renouvellements simultanés du même jeton passent l'un après l'autre.
        query = query.with_for_update()
    return db.scalar(query)


def revoke_family(db: Session, family_id: uuid.UUID, *, reason: str, now: datetime) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason=reason)
    )


def delete_expired_refresh_tokens(db: Session, *, before: datetime) -> int:
    result = db.execute(delete(RefreshToken).where(RefreshToken.expires_at < before))
    return result.rowcount


def active_sessions(db: Session, user_id: int, *, now: datetime) -> list[RefreshToken]:
    """Le jeton en cours de chaque session active (un seul non révoqué par famille)."""
    query = (
        select(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        .order_by(RefreshToken.created_at.desc())
    )
    return list(db.scalars(query))


def revoke_user_families(
    db: Session,
    user_id: int,
    *,
    reason: str,
    now: datetime,
    only: uuid.UUID | None = None,
    keep: uuid.UUID | None = None,
) -> int:
    """Révoque les sessions d'un utilisateur : une seule (`only`), ou toutes sauf `keep`."""
    query = update(RefreshToken).where(
        RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
    )
    if only is not None:
        query = query.where(RefreshToken.family_id == only)
    if keep is not None:
        query = query.where(RefreshToken.family_id != keep)
    return db.execute(query.values(revoked_at=now, revoked_reason=reason)).rowcount


# --- Administration des utilisateurs et des rôles --------------------------------


def roles_in_company(db: Session, user_id: int, company_id: int) -> list[Role]:
    query = (
        select(Role)
        .join(UserCompanyRole, UserCompanyRole.role_id == Role.id)
        .where(UserCompanyRole.user_id == user_id, UserCompanyRole.company_id == company_id)
        .order_by(Role.name)
    )
    return list(db.scalars(query))


def company_counts(db: Session, user_ids: list[int]) -> dict[int, int]:
    """Nombre de sociétés auxquelles chaque utilisateur a accès."""
    if not user_ids:
        return {}
    query = (
        select(UserCompanyRole.user_id, func.count(func.distinct(UserCompanyRole.company_id)))
        .where(UserCompanyRole.user_id.in_(user_ids))
        .group_by(UserCompanyRole.user_id)
    )
    return {user_id: count for user_id, count in db.execute(query).all()}


def role_user_counts(db: Session) -> dict[int, int]:
    query = select(
        UserCompanyRole.role_id, func.count(func.distinct(UserCompanyRole.user_id))
    ).group_by(UserCompanyRole.role_id)
    return {role_id: count for role_id, count in db.execute(query).all()}


def revoke_company_access(db: Session, company_id: int) -> int:
    """Retire tous les rôles attribués dans une société (avant sa suppression)."""
    result = db.execute(delete(UserCompanyRole).where(UserCompanyRole.company_id == company_id))
    return result.rowcount
