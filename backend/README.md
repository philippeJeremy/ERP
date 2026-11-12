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

## Connexion et sessions

- `POST /auth/login` renvoie un **jeton d'accès** JWT (15 min) et pose un **refresh
  token** dans un cookie `httpOnly` (chemin `/api/auth`).
- **Durée d'une session** (variables `SESSION_IDLE_MINUTES`, `SESSION_MAX_HOURS`) :
  - **30 min d'inactivité** : sans requête pendant ce délai, la session expire ;
    chaque renouvellement repousse l'échéance (expiration « glissante ») ;
  - **12 h maximum** : quoi qu'il arrive, reconnexion au bout de 12 h.
- `POST /auth/refresh` échange le cookie contre un nouveau jeton d'accès, et remplace
  le cookie (rotation). Un ancien jeton rejoué plus de 10 s après son remplacement
  est considéré comme volé : toute la session est révoquée.
- `POST /auth/logout` révoque la session.
- Profil : `PATCH /auth/me` (nom), `POST /auth/me/password` (ferme les autres
  sessions), `GET /auth/me/sessions`, `DELETE /auth/me/sessions/{id}`,
  `POST /auth/me/sessions/revoke-others`.
- Les sessions sont en base (`auth.refresh_tokens`, empreinte SHA-256 seulement) ;
  le worker supprime chaque nuit celles expirées depuis 30 jours.

## Mot de passe provisoire et sociétés

- Un compte créé ou réinitialisé par un administrateur a `must_change_password = true` :
  tant que l'utilisateur n'a pas choisi son mot de passe (`POST /auth/me/password`),
  l'API ne lui répond que sur `GET /auth/me` (403 `mot_de_passe_a_changer` ailleurs).
- Sociétés : `POST /org/companies` et `DELETE /org/companies/{id}` (super-admin),
  `PATCH /org/companies/{id}` (`org:manage`, société courante ; activation réservée au
  super-admin). Une société désactivée n'est plus accessible à ses utilisateurs
  (403 `societe_desactivee`). La suppression ne vaut que pour une société vide : dès
  qu'elle contient des données, PostgreSQL la refuse (409 `societe_non_vide`) et on
  la désactive à la place. SIREN unique (409 `siren_existant`).

## Administration des utilisateurs et des rôles

| Route | Droit | Rôle |
|---|---|---|
| `GET /auth/users`, `GET /auth/users/{id}` | `auth:read` | Utilisateurs de la société courante |
| `POST /auth/users` | `auth:manage` | Créer un compte (au moins un rôle) |
| `POST /auth/users/attach` | `auth:manage` | Donner accès à la société à un compte existant |
| `PATCH /auth/users/{id}` | `auth:manage` | Nom, e-mail, activation (désactiver ferme ses sessions) |
| `POST /auth/users/{id}/password` | `auth:manage` | Réinitialiser le mot de passe (ferme ses sessions) |
| `PUT /auth/users/{id}/roles` | `auth:manage` | Remplacer ses rôles dans la société (vide = retirer l'accès) |
| `POST/PATCH/DELETE /auth/roles…` | super-admin | Rôles, communs à tout le groupe |

Règles anti-escalade (dans `auth/service.py`, testées dans `tests/test_admin_utilisateurs.py`) :
- on n'attribue et on ne retire qu'un rôle dont on possède **toutes** les permissions ;
- on ne modifie pas ses propres rôles, on ne désactive pas son propre compte ;
- on ne modifie l'identité ou le mot de passe d'un compte que s'il n'a pas plus de droits
  que soi et n'a accès qu'à la société courante (sinon : super-administrateur) ;
- un rôle système, ou encore attribué, ne se supprime pas.

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
