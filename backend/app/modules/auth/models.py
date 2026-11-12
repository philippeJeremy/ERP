"""Schéma PostgreSQL `auth` : utilisateurs, rôles, permissions, accès par société.

Modèle des droits :
  - un RÔLE (ex. « Commercial ») = une liste de permissions (« sales:write »…) ;
  - un utilisateur reçoit des rôles DANS une société (table user_company_roles) :
    admin dans la filiale A, simple lecture dans la filiale B ;
  - avoir au moins un rôle dans une société = y avoir accès.
Les permissions elles-mêmes sont déclarées dans le code (permissions.py de chaque
module) : pas de table à synchroniser, le code est la référence.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Identity, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models import CURRENT_USER_ID, Base, BusinessEntity


class User(Base, BusinessEntity):
    __tablename__ = "users"
    __table_args__ = {"schema": "auth"}

    email: Mapped[str] = mapped_column(String(254))
    full_name: Mapped[str] = mapped_column(String(150))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(server_default="true")
    # Super-administrateur : tous les droits partout, crée les sociétés.
    is_superuser: Mapped[bool] = mapped_column(server_default="false")
    # Mot de passe provisoire (compte créé ou réinitialisé par un administrateur) :
    # l'utilisateur doit en choisir un nouveau avant de pouvoir utiliser l'ERP.
    must_change_password: Mapped[bool] = mapped_column(server_default="false")
    last_login_at: Mapped[datetime | None]


# Unicité insensible à la casse : « Jean@x.fr » et « jean@x.fr » = même compte.
Index("uq_users_email_lower", func.lower(User.email), unique=True)


class Role(Base, BusinessEntity):
    __tablename__ = "roles"
    __table_args__ = {"schema": "auth"}

    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    # Rôle système (« admin ») : créé par les migrations, non modifiable par l'interface.
    is_system: Mapped[bool] = mapped_column(server_default="false")

    permissions: Mapped[list["RolePermission"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="RolePermission.permission"
    )

    @property
    def permission_codes(self) -> list[str]:
        return [p.permission for p in self.permissions]


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = {"schema": "auth"}

    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("auth.roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission: Mapped[str] = mapped_column(String(100), primary_key=True)


class UserCompanyRole(Base):
    __tablename__ = "user_company_roles"
    __table_args__ = {"schema": "auth"}

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("auth.users.id", ondelete="CASCADE"), primary_key=True
    )
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("org.companies.id"), primary_key=True, index=True
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("auth.roles.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("auth.users.id"), server_default=CURRENT_USER_ID
    )

    role: Mapped[Role] = relationship(lazy="joined")


class RefreshToken(Base):
    """Une session de connexion (un navigateur), renouvelée par rotation.

    Chaque jeton expire après le délai d'inactivité ; le renouvellement repousse
    l'échéance (expiration « glissante »), sans jamais dépasser la durée maximale
    de la session.

    À chaque utilisation, le jeton est révoqué et remplacé par un nouveau de la même
    « famille ». Si un jeton déjà remplacé est présenté à nouveau, c'est qu'il a été
    volé et rejoué : toute la famille est révoquée (le voleur ET l'utilisateur sont
    déconnectés, l'utilisateur se reconnecte, le voleur non).
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        CheckConstraint(
            "revoked_reason IN ('rotated', 'logout', 'reuse', 'disabled')", name="revoked_reason"
        ),
        {"schema": "auth"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("auth.users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # Début de la session (la connexion), recopié à chaque rotation : sert à appliquer
    # la durée maximale de session.
    session_started_at: Mapped[datetime]
    # min(maintenant + délai d'inactivité, début de session + durée maximale)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    revoked_reason: Mapped[str | None] = mapped_column(String(20))
    user_agent: Mapped[str | None] = mapped_column(String(255))
