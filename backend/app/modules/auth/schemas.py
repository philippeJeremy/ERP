from datetime import datetime

from pydantic import EmailStr, Field

from app.shared.schemas import ReadSchema, Schema


class Token(Schema):
    access_token: str
    token_type: str = "bearer"


class RoleRef(ReadSchema):
    id: int
    code: str
    name: str


class CompanyAccess(Schema):
    """Accès d'un utilisateur à une société : ses rôles et ses permissions effectives."""

    company_id: int
    roles: list[RoleRef]


class UserRead(ReadSchema):
    id: int
    email: str
    full_name: str
    is_active: bool
    is_superuser: bool
    last_login_at: datetime | None


class Me(Schema):
    user: UserRead
    companies: list[CompanyAccess]
    # Permissions dans la société courante (en-tête X-Company-Id), pour que le front
    # masque les boutons inutiles. Le contrôle réel reste fait par l'API.
    current_company_id: int | None
    permissions: list[str]


class UserCreate(Schema):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=12, max_length=128)
    role_ids: list[int] = Field(default_factory=list, description="Rôles dans la société courante")


class UserInCompany(UserRead):
    roles: list[RoleRef]


class RoleCreate(Schema):
    code: str = Field(min_length=1, max_length=50, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)


class RoleRead(ReadSchema):
    id: int
    code: str
    name: str
    description: str | None
    is_system: bool
    permissions: list[str] = Field(validation_alias="permission_codes")


class RolePermissionsUpdate(Schema):
    permissions: list[str]


class RoleAssignment(Schema):
    role_id: int


class PermissionInfo(Schema):
    code: str
    label: str
