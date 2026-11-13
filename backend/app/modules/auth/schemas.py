import uuid
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
    must_change_password: bool = False
    last_login_at: datetime | None


class Me(Schema):
    user: UserRead
    companies: list[CompanyAccess]
    # Permissions dans la société courante (en-tête X-Company-Id), pour que le front
    # masque les boutons inutiles. Le contrôle réel reste fait par l'API.
    current_company_id: int | None
    permissions: list[str]
    # Le frontend déconnecte l'écran après ce délai sans activité de l'utilisateur.
    session_idle_minutes: int


class UserCreate(Schema):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=12, max_length=128)
    role_ids: list[int] = Field(default_factory=list, description="Rôles dans la société courante")


class UserInCompany(UserRead):
    roles: list[RoleRef]
    # Vrai si le compte a aussi accès à d'autres sociétés : seul un super-administrateur
    # peut alors modifier son identité (nom, e-mail, mot de passe, activation).
    multi_company: bool = False


class UserUpdate(Schema):
    """Modification partielle d'un compte par un administrateur."""

    full_name: str | None = Field(None, min_length=1, max_length=150)
    email: EmailStr | None = None
    is_active: bool | None = None


class UserAttach(Schema):
    """Donner accès à la société courante à un compte qui existe déjà."""

    email: EmailStr
    role_ids: list[int]


class UserRolesUpdate(Schema):
    """Liste complète des rôles de l'utilisateur dans la société courante.
    Liste vide = retirer son accès à la société."""

    role_ids: list[int]


class CompanyAccessInfo(Schema):
    """Accès d'un utilisateur à une société, vu par l'administrateur connecté."""

    company_id: int
    roles: list[RoleRef]
    # L'administrateur connecté peut-il modifier ces rôles (droit auth:manage dans
    # cette société, et ce n'est pas son propre compte) ?
    can_manage: bool
    # Rôles qu'il a le droit d'attribuer DANS cette société (règle anti-escalade).
    grantable_role_ids: list[int]
    # Droits individuels de l'utilisateur dans cette société (en plus de ses rôles).
    extra_permissions: list[str] = []
    # Droits individuels que l'administrateur connecté peut accorder (ceux qu'il a).
    grantable_permissions: list[str] = []


class UserPermissionsUpdate(Schema):
    """Liste complète des droits individuels dans une société (remplace l'existante)."""

    permissions: list[str]


class PasswordReset(Schema):
    new_password: str = Field(min_length=12, max_length=128)


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
    user_count: int = 0  # nombre d'utilisateurs qui ont ce rôle (toutes sociétés)


class RoleUpdate(Schema):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    permissions: list[str] | None = None


class RolePermissionsUpdate(Schema):
    permissions: list[str]


class RoleAssignment(Schema):
    role_id: int


class PermissionInfo(Schema):
    code: str
    label: str


class ProfileUpdate(Schema):
    full_name: str = Field(min_length=1, max_length=150)


class PasswordChange(Schema):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class SessionInfo(Schema):
    """Une session ouverte (un navigateur / appareil)."""

    id: uuid.UUID  # identifiant de la famille de jetons
    started_at: datetime  # connexion
    last_used_at: datetime  # dernier renouvellement
    expires_at: datetime  # sans activité, fin de la session à cette heure
    user_agent: str | None
    current: bool  # la session de ce navigateur
