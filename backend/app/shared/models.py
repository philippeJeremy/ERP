"""Base SQLAlchemy commune et mixins réutilisés par tous les modules.

Un mixin = un groupe de colonnes qu'on « ajoute » à une table en héritant de la classe.
Ainsi, les conventions (types, horodatage, traçabilité) sont écrites une seule fois.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    MetaData,
    Numeric,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# Noms de contraintes prévisibles. Sans ça, PostgreSQL invente des noms et Alembic ne
# sait plus les retrouver pour les supprimer ou les renommer dans une migration.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Valeurs lues dans le contexte de la transaction (voir app/core/db.py).
# NULLIF(…, '') : un paramètre jamais défini, ou remis à zéro, vaut '' et non NULL.
CURRENT_USER_ID = text("NULLIF(current_setting('app.user_id', true), '')::bigint")
CURRENT_COMPANY_ID = text("NULLIF(current_setting('app.company_id', true), '')::bigint")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # Types par défaut selon l'annotation Python.
    type_annotation_map = {
        datetime: DateTime(timezone=True),  # TIMESTAMPTZ, toujours stocké en UTC
        Decimal: Numeric(14, 2),  # montants : jamais de float
    }


class IdMixin:
    """Clé primaire technique BIGINT générée par PostgreSQL."""

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class TrackedByMixin:
    """Qui a créé / modifié la ligne. Rempli automatiquement depuis `app.user_id`."""

    @declared_attr
    def created_by(cls) -> Mapped[int | None]:
        return mapped_column(
            BigInteger, ForeignKey("auth.users.id"), server_default=CURRENT_USER_ID
        )

    @declared_attr
    def updated_by(cls) -> Mapped[int | None]:
        return mapped_column(
            BigInteger,
            ForeignKey("auth.users.id"),
            server_default=CURRENT_USER_ID,
            onupdate=CURRENT_USER_ID,
        )


class VersionMixin:
    """Verrouillage optimiste.

    SQLAlchemy ajoute `WHERE version = <valeur lue>` à chaque UPDATE et incrémente la
    version. Si quelqu'un a modifié la ligne entre-temps, aucune ligne ne correspond
    → StaleDataError → HTTP 409 au lieu d'écraser silencieusement son travail.
    """

    version: Mapped[int] = mapped_column(server_default="1")

    @declared_attr.directive
    def __mapper_args__(cls) -> dict:
        return {"version_id_col": cls.version}


class CompanyScopedMixin:
    """Ligne appartenant à UNE société. Protégée par la Row-Level Security.

    `company_id` prend par défaut la société courante de la transaction.
    """

    @declared_attr
    def company_id(cls) -> Mapped[int]:
        return mapped_column(
            BigInteger,
            ForeignKey("org.companies.id"),
            index=True,
            server_default=CURRENT_COMPANY_ID,
        )


class SharedOrCompanyMixin:
    """Ligne partagée par tout le groupe (company_id NULL) ou réservée à une société."""

    @declared_attr
    def company_id(cls) -> Mapped[int | None]:
        return mapped_column(BigInteger, ForeignKey("org.companies.id"), index=True)


class BusinessEntity(IdMixin, TimestampMixin, TrackedByMixin, VersionMixin):
    """Raccourci pour les entités métier : id + horodatage + traçabilité + version."""
