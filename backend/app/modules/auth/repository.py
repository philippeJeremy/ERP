from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.modules.auth.models import Role, RolePermission, User, UserCompanyRole


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
