"""Socle : schémas, journal d'audit, utilisateurs/rôles (auth), sociétés (org).

Revision ID: 0001
Revises:
Create Date: 2026-11-11

Cette première migration est écrite en partie à la main : en plus des tables
(générées par `alembic revision --autogenerate`), elle crée ce qu'Alembic ne sait
pas détecter tout seul — schémas et droits, fonction d'audit, triggers, RLS,
rôle système « admin ».
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.shared.migrations import (
    APP_ROLE,
    create_module_schema,
    drop_module_schema,
    enable_audit,
    enable_company_rls,
)

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MODULE_SCHEMAS = ["auth", "org"]

AUDIT_FUNCTION = """
CREATE OR REPLACE FUNCTION audit.log_change() RETURNS trigger
LANGUAGE plpgsql
-- SECURITY DEFINER : la fonction s'exécute avec les droits de son propriétaire
-- (erp_owner). L'API (erp_app) peut donc ÉCRIRE dans le journal via les triggers,
-- sans avoir le droit d'y écrire directement, ni de le modifier ou l'effacer.
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    -- COALESCE : sans argument, TG_ARGV vaut NULL, et « jsonb - NULL » donnerait NULL.
    excluded text[] := COALESCE(TG_ARGV::text[], '{}');
    old_row  jsonb;
    new_row  jsonb;
    changed  text[];
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        old_row := to_jsonb(OLD) - excluded;
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        new_row := to_jsonb(NEW) - excluded;
    END IF;

    IF TG_OP = 'UPDATE' THEN
        SELECT array_agg(n.key ORDER BY n.key) INTO changed
        FROM jsonb_each(new_row) AS n
        WHERE n.value IS DISTINCT FROM old_row -> n.key
          AND n.key NOT IN ('updated_at', 'updated_by', 'version');
        IF changed IS NULL THEN
            RETURN NULL;  -- rien de significatif n'a changé : on ne journalise pas
        END IF;
    END IF;

    INSERT INTO audit.audit_log
        (user_id, company_id, schema_name, table_name, record_id, action,
         old_data, new_data, changed_fields)
    VALUES (
        NULLIF(current_setting('app.user_id', true), '')::bigint,
        NULLIF(current_setting('app.company_id', true), '')::bigint,
        TG_TABLE_SCHEMA, TG_TABLE_NAME,
        COALESCE(new_row ->> 'id', old_row ->> 'id'),
        TG_OP, old_row, new_row, changed
    );
    RETURN NULL;  -- trigger AFTER : la valeur de retour est ignorée
END;
$$
"""


def upgrade() -> None:
    # --- 1. Schémas des modules + droits de erp_app ---------------------------------
    for schema in MODULE_SCHEMAS:
        create_module_schema(schema)

    # --- 2. Journal d'audit ------------------------------------------------------------
    # Schéma à part : erp_app peut LIRE le journal (écran d'historique) mais pas l'écrire.
    op.execute("CREATE SCHEMA audit")
    op.execute(f"GRANT USAGE ON SCHEMA audit TO {APP_ROLE}")
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.BigInteger()),
        sa.Column("company_id", sa.BigInteger()),
        sa.Column("schema_name", sa.Text(), nullable=False),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column("record_id", sa.Text()),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("old_data", sa.dialects.postgresql.JSONB()),
        sa.Column("new_data", sa.dialects.postgresql.JSONB()),
        sa.Column("changed_fields", sa.dialects.postgresql.ARRAY(sa.Text())),
        sa.CheckConstraint("action IN ('INSERT', 'UPDATE', 'DELETE')", name="ck_audit_log_action"),
        schema="audit",
    )
    # Index pour « l'historique de CETTE fiche » et « l'activité récente ».
    op.create_index(
        "ix_audit_log_record",
        "audit_log",
        ["schema_name", "table_name", "record_id"],
        schema="audit",
    )
    op.create_index("ix_audit_log_occurred_at", "audit_log", ["occurred_at"], schema="audit")
    op.execute(f"GRANT SELECT ON audit.audit_log TO {APP_ROLE}")
    op.execute(AUDIT_FUNCTION)
    op.execute("REVOKE ALL ON FUNCTION audit.log_change() FROM PUBLIC")

    # --- 3. Tables (générées par Alembic) -------------------------------------------
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_superuser", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            server_default=sa.text("NULLIF(current_setting('app.user_id', true), '')::bigint"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            sa.BigInteger(),
            server_default=sa.text("NULLIF(current_setting('app.user_id', true), '')::bigint"),
            nullable=True,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["auth.users.id"], name=op.f("fk_users_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["auth.users.id"], name=op.f("fk_users_updated_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        schema="auth",
    )
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.literal_column("lower(email)")],
        unique=True,
        schema="auth",
    )
    op.create_table(
        "roles",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            server_default=sa.text("NULLIF(current_setting('app.user_id', true), '')::bigint"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            sa.BigInteger(),
            server_default=sa.text("NULLIF(current_setting('app.user_id', true), '')::bigint"),
            nullable=True,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["auth.users.id"], name=op.f("fk_roles_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["auth.users.id"], name=op.f("fk_roles_updated_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("code", name=op.f("uq_roles_code")),
        schema="auth",
    )
    op.create_table(
        "companies",
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("legal_form", sa.String(length=50), nullable=True),
        sa.Column("siren", sa.String(length=9), nullable=True),
        sa.Column("vat_number", sa.String(length=20), nullable=True),
        sa.Column("address_line1", sa.String(length=200), nullable=True),
        sa.Column("address_line2", sa.String(length=200), nullable=True),
        sa.Column("postal_code", sa.String(length=10), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("country_code", sa.String(length=2), server_default="FR", nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("iban", sa.String(length=34), nullable=True),
        sa.Column("bic", sa.String(length=11), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default="EUR", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            server_default=sa.text("NULLIF(current_setting('app.user_id', true), '')::bigint"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            sa.BigInteger(),
            server_default=sa.text("NULLIF(current_setting('app.user_id', true), '')::bigint"),
            nullable=True,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "country_code ~ '^[A-Z]{2}$'", name=op.f("ck_companies_country_code_format")
        ),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_companies_currency_format")),
        sa.CheckConstraint("siren ~ '^[0-9]{9}$'", name=op.f("ck_companies_siren_format")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["auth.users.id"], name=op.f("fk_companies_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["auth.users.id"], name=op.f("fk_companies_updated_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
        sa.UniqueConstraint("code", name=op.f("uq_companies_code")),
        sa.UniqueConstraint("siren", name=op.f("uq_companies_siren")),
        schema="org",
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("permission", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["auth.roles.id"],
            name=op.f("fk_role_permissions_role_id_roles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission", name=op.f("pk_role_permissions")),
        schema="auth",
    )
    op.create_table(
        "user_company_roles",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            server_default=sa.text("NULLIF(current_setting('app.user_id', true), '')::bigint"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["org.companies.id"],
            name=op.f("fk_user_company_roles_company_id_companies"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["auth.users.id"], name=op.f("fk_user_company_roles_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["auth.roles.id"],
            name=op.f("fk_user_company_roles_role_id_roles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name=op.f("fk_user_company_roles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "company_id", "role_id", name=op.f("pk_user_company_roles")
        ),
        schema="auth",
    )
    op.create_index(
        op.f("ix_user_company_roles_company_id"),
        "user_company_roles",
        ["company_id"],
        unique=False,
        schema="auth",
    )
    op.create_table(
        "number_sequences",
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("prefix", sa.String(length=30), nullable=False),
        sa.Column("padding", sa.Integer(), server_default="5", nullable=False),
        sa.Column("next_value", sa.BigInteger(), server_default="1", nullable=False),
        sa.Column("reset_yearly", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("current_year", sa.Integer(), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.BigInteger(),
            server_default=sa.text("NULLIF(current_setting('app.company_id', true), '')::bigint"),
            nullable=False,
        ),
        sa.CheckConstraint("next_value >= 1", name=op.f("ck_number_sequences_next_value_positive")),
        sa.CheckConstraint(
            "padding BETWEEN 1 AND 12", name=op.f("ck_number_sequences_padding_range")
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["org.companies.id"],
            name=op.f("fk_number_sequences_company_id_companies"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_number_sequences")),
        sa.UniqueConstraint("company_id", "code", name=op.f("uq_number_sequences_company_id_code")),
        schema="org",
    )
    op.create_index(
        op.f("ix_number_sequences_company_id"),
        "number_sequences",
        ["company_id"],
        unique=False,
        schema="org",
    )

    # --- 4. Row-Level Security ---------------------------------------------------------
    # Les compteurs de numérotation appartiennent à une société.
    enable_company_rls("org.number_sequences")

    # --- 5. Audit -----------------------------------------------------------------------
    # Mot de passe jamais copié dans le journal ; la date de dernière connexion,
    # modifiée à chaque login, noierait le journal.
    enable_audit("auth.users", exclude=("password_hash", "last_login_at"))
    enable_audit("auth.roles")
    enable_audit("auth.role_permissions")
    enable_audit("auth.user_company_roles")
    enable_audit("org.companies")
    enable_audit("org.number_sequences")

    # --- 6. Rôle système « admin » : toutes les permissions dans sa société ----------------
    op.execute(
        "INSERT INTO auth.roles (code, name, description, is_system) VALUES "
        "('admin', 'Administrateur', 'Tous les droits dans la société', true)"
    )
    op.execute(
        "INSERT INTO auth.role_permissions (role_id, permission) "
        "SELECT id, '*' FROM auth.roles WHERE code = 'admin'"
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_number_sequences_company_id"), table_name="number_sequences", schema="org"
    )
    op.drop_table("number_sequences", schema="org")
    op.drop_index(
        op.f("ix_user_company_roles_company_id"), table_name="user_company_roles", schema="auth"
    )
    op.drop_table("user_company_roles", schema="auth")
    op.drop_table("role_permissions", schema="auth")
    op.drop_table("companies", schema="org")
    op.drop_table("roles", schema="auth")
    op.drop_index("uq_users_email_lower", table_name="users", schema="auth")
    op.drop_table("users", schema="auth")
    op.execute("DROP SCHEMA IF EXISTS audit CASCADE")
    for schema in reversed(MODULE_SCHEMAS):
        drop_module_schema(schema)
