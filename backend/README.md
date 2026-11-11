# Backend de l'ERP

API FastAPI organisée en **monolithe modulaire**, sur PostgreSQL.

## Démarrer (depuis la racine du dépôt)

```bash
cp .env.example .env                                    # à la racine, puis remplir les secrets
cp docker-compose.override.example.yaml docker-compose.override.yaml   # en dev seulement
docker compose up -d --build
docker compose run --rm api python -m app.cli bootstrap \
    --email admin@exemple.fr --name "Admin" --company-code HOLD --company-name "Ma Holding"
```

Documentation interactive (dev) : http://127.0.0.1:8000/docs. Utiliser le bouton
**Authorize** pour se connecter, puis renseigner l'en-tête `X-Company-Id`.

## Organisation du code

```
app/
├── main.py            création de l'app, /health, /ready
├── cli.py             commandes d'administration (bootstrap)
├── core/              technique transverse : config, db, sécurité, erreurs, contexte
├── shared/            Base SQLAlchemy, mixins, schémas Pydantic de base, helpers de migration
├── modules/           un dossier par domaine métier (liste dans modules/__init__.py)
│   └── <module>/
│       ├── models.py      tables (privé au module)
│       ├── schemas.py     entrées / sorties de l'API
│       ├── repository.py  requêtes SQL uniquement
│       ├── service.py     règles métier, commit des transactions
│       ├── router.py      routes HTTP (fines)
│       ├── permissions.py permissions déclarées par le module
│       └── public.py      la SEULE interface que les autres modules importent
└── workers/           tâches de fond ARQ
```

## Base de données

- **Un schéma PostgreSQL par module** (`auth`, `org`, …) + `audit`.
- **Deux rôles** : `erp_owner` (propriétaire, migrations) et `erp_app` (l'API : données
  seulement, pas de DDL, soumis à la RLS, ne peut pas modifier le journal d'audit).
- **Multi-société** : l'API transmet à PostgreSQL l'utilisateur et la société courante
  (`app.user_id`, `app.company_id`). La **Row-Level Security** isole les sociétés.
  Les colonnes `company_id`, `created_by` et `updated_by` se remplissent toutes seules.
- **Audit** : trigger `audit.log_change()` (qui, quand, société, anciennes / nouvelles valeurs).

## Ajouter une table métier

1. Modèle dans `modules/<module>/models.py` (hériter de `BusinessEntity` et de
   `CompanyScopedMixin` ou `SharedOrCompanyMixin`).
2. `alembic revision --autogenerate -m "..."` puis relire le fichier généré.
3. Dans la migration, ajouter `enable_company_rls("schema.table")` et
   `enable_audit("schema.table")`.
4. Un nouveau schéma ? `create_module_schema("nom")` en tête de migration.

## Tests

```bash
pip install ".[dev]"
pytest                       # tests unitaires seuls
# + tests d'intégration sur un PostgreSQL migré :
TEST_DATABASE_URL=postgresql+psycopg://erp_app:...@127.0.0.1:5432/erp \
TEST_MIGRATION_DATABASE_URL=postgresql+psycopg://erp_owner:...@127.0.0.1:5432/erp pytest
```
