"""Briques réutilisables dans les migrations Alembic.

Les migrations sont exécutées par le rôle `erp_owner` (propriétaire des tables).
L'API, elle, se connecte avec `erp_app`, qui n'a que les droits sur les DONNÉES.
"""

import os

from alembic import op

APP_ROLE = os.environ.get("ERP_APP_ROLE", "erp_app")


def create_module_schema(schema: str) -> None:
    """Crée le schéma d'un module et donne à erp_app les droits de lecture/écriture.

    `ALTER DEFAULT PRIVILEGES` : les droits s'appliquent aussi aux tables créées PLUS
    TARD dans ce schéma par erp_owner. Pas besoin de penser au GRANT à chaque table.
    """
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    op.execute(f"GRANT USAGE ON SCHEMA {schema} TO {APP_ROLE}")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
        f"GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"
    )


def drop_module_schema(schema: str) -> None:
    op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")


_CURRENT_COMPANY = "NULLIF(current_setting('app.company_id', true), '')::bigint"


def enable_company_rls(table: str, *, shared: bool = False) -> None:
    """Active la Row-Level Security « une société ne voit que ses lignes ».

    - USING      : quelles lignes sont visibles (SELECT, UPDATE, DELETE) ;
    - WITH CHECK : quelles lignes on a le droit d'écrire (INSERT, UPDATE).
    shared=True  : company_id NULL = ligne partagée par tout le groupe, visible de tous.

    Sans société courante (app.company_id vide), aucune ligne n'est visible : le
    comportement par défaut est fermé, pas ouvert.
    Le propriétaire des tables (erp_owner) n'est pas soumis à la RLS : les migrations
    et corrections de données restent possibles.
    """
    own = f"company_id = {_CURRENT_COMPANY}"
    rule = f"company_id IS NULL OR {own}" if shared else own
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY company_isolation ON {table} "
        f"FOR ALL TO {APP_ROLE} USING ({rule}) WITH CHECK ({rule})"
    )


def enable_audit(table: str, *, exclude: tuple[str, ...] = ()) -> None:
    """Branche le journal d'audit sur une table (trigger AFTER INSERT/UPDATE/DELETE).

    `exclude` : colonnes à ne jamais copier dans le journal (ex. password_hash) ou
    trop bavardes (ex. last_login_at). Une mise à jour qui ne touche QUE ces colonnes
    n'est pas journalisée.
    """
    name = table.split(".")[-1]
    args = ", ".join(f"'{col}'" for col in exclude)
    op.execute(
        f"CREATE TRIGGER audit_{name} AFTER INSERT OR UPDATE OR DELETE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION audit.log_change({args})"
    )
