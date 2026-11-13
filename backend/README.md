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
| `GET /org/user-access/{id}` | connecté | Ses rôles dans chacune de VOS sociétés (+ ce que vous pouvez y attribuer) |
| `PUT /auth/users/{id}/companies/{company_id}/roles` | `auth:manage` dans cette société | Donner / modifier / retirer l'accès à une société |
| `PUT /auth/users/{id}/companies/{company_id}/permissions` | `auth:manage` dans cette société | Droits individuels, en plus des rôles |
| `POST/PATCH/DELETE /auth/roles…` | super-admin | Rôles, communs à tout le groupe |

Règles anti-escalade (dans `auth/service.py`, testées dans `tests/test_admin_utilisateurs.py`) :
- on n'attribue et on ne retire qu'un rôle dont on possède **toutes** les permissions ;
- on ne modifie pas ses propres rôles, on ne désactive pas son propre compte ;
- on ne modifie l'identité ou le mot de passe d'un compte que s'il n'a pas plus de droits
  que soi et n'a accès qu'à la société courante (sinon : super-administrateur) ;
- un rôle système, ou encore attribué, ne se supprime pas ;
- droits individuels : on n'accorde ou ne retire que des droits qu'on a soi-même ; il
  faut un rôle dans la société (au minimum le rôle système « Membre », sans droit) ;
  retirer tous les rôles supprime aussi les droits individuels.

Droits effectifs dans une société = droits des rôles + droits individuels
(`auth.user_company_permissions`).

## Tiers (fournisseurs)

Module `partners` : une seule table de tiers avec des rôles (`is_supplier`,
`is_customer`), propre à chaque société (Row-Level Security). Code automatique `T00001`
(compteur `partner` de `org.number_sequences`, sans remise à zéro annuelle).

| Route | Permission | Rôle |
|---|---|---|
| `GET /partners?role=supplier&q=&active=&sort=&order=&limit=&offset=` | `partners:read` | Liste paginée `{items, total}` (recherche : code, nom, SIRET, e-mail, contact) |
| `GET /partners/{id}` | `partners:read` | Fiche avec adresses et contacts |
| `POST /partners`, `PATCH /partners/{id}` | `partners:manage` | Créer / modifier (`version` obligatoire au PATCH) |
| `DELETE /partners/{id}` | `partners:manage` | Supprimer une fiche sans historique (sinon 409 : désactiver) |
| `POST/PUT/DELETE /partners/{id}/addresses…`, `…/contacts…` | `partners:manage` | Adresses (siège, commande, enlèvement, retour…) et contacts |

Contrôles : SIRET 14 chiffres et unique par société, IBAN (clé modulo 97), BIC,
pas de boucle dans les groupements ; une seule adresse principale par type et un seul
interlocuteur principal.

## Catalogue et imports tarifs (module `catalog`)

- **Articles communs au groupe** (pas de RLS) : `catalog.articles` (code `A0000001`
  tiré d'une séquence, EAN unique et vérifié, marque, désignation, type pneu / pièce /
  accessoire), `catalog.brands`, `catalog.tire_specs` (dimension, indices, saison, type
  de véhicule, XL, runflat, 3PMSF, étiquette UE, n° EPREL ; `size_code` « 2055516 »
  pour la recherche). `tires.py` lit la dimension dans une désignation.
- **Par société** (RLS) : `article_suppliers` (référence fournisseur, prix d'achat à
  4 décimales, préféré, arrêté), `import_profiles`, `import_runs`, `import_lines`.
- Permissions : `catalog:read`, `catalog:manage`, `catalog:import`.

Import d'un tarif : `POST /catalog/imports/preview` (10 premières lignes + correspondance
proposée) → profil (`/catalog/import-profiles`, mémorisé par fournisseur) →
`POST /catalog/imports` (fichier stocké en base, analyse en tâche de fond) →
`GET /catalog/imports/{id}` et `/lines?status=` (aperçu) → `POST …/apply`
(une transaction, tout ou rien) ou `…/cancel`. Un import ne modifie jamais une fiche
article existante (catalogue commun), seulement le prix et le statut chez ce fournisseur.
Fichier complet : les articles absents sont arrêtés ; au-delà de 30 % (et 10 articles),
`confirm_discontinue` est exigé (409 `confirmation_requise`).

Tâches de fond : `app/core/jobs.py` (`@job("nom")`, `enqueue("nom", …)`), exécutées par
le worker ARQ ; `JOBS_INLINE=true` les exécute dans l'API (tests, dev sans worker).

## Relèves automatiques des tarifs (FTP / FTPS / SFTP)

Table `catalog.import_sources` (par société) : serveur, identifiant, secret **chiffré**
(`app/core/secrets.py`, Fernet, clé `SECRETS_KEY`), dossier, motif (`tarif_*.csv`),
fréquence, application automatique. `catalog.import_source_files` retient les fichiers
déjà vus (nom + taille + date) : seul le plus récent des nouveaux est importé, et on ne
modifie jamais les fichiers du fournisseur.

- Le worker lance toutes les 5 minutes `catalog.poll_due_sources` : la fonction SQL
  `catalog.due_import_sources()` (SECURITY DEFINER) liste les relèves dues de toutes
  les sociétés, puis chacune est traitée avec le contexte de sa société (RLS).
- `app/modules/catalog/remote.py` : délais de 20 s, adresses internes refusées sauf
  `IMPORT_ALLOW_PRIVATE_HOSTS=true`, empreinte SSH vérifiée (confirmée au test de
  connexion), certificat FTPS vérifié (désactivable par relève), taille maximale.
- Application automatique seulement si l'analyse est propre (pas de confirmation
  d'arrêts nécessaire, moins de 5 % de lignes en erreur) ; sinon l'import attend.

Générer la clé : `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

## Achats (module `purchasing`) et dépôts

- `org.sites` : dépôts de chaque société (adresse de livraison, consignes, GLN, dépôt par
  défaut). `GET /org/sites` pour tous, écriture `org:manage`.
- `purchasing.orders` / `order_lines` : brouillon → (à valider) → validée → envoyée →
  confirmée → partielle / reçue ; clôturée ou annulée. Le numéro `CF-…` est attribué à la
  validation (`org.next_number`), pas à la création du brouillon. Seuil de validation par
  société (`purchasing.settings`) : au-delà, `purchasing:approve` requis, et on
  n'approuve pas sa propre commande.
- Prix et référence repris du lien article-fournisseur du catalogue ; alertes minimum de
  commande, franco, article non référencé ou arrêté. Total au centime (arrondi commercial).
- `receptions` / `reception_lines` (`BR-…`) : quantités reçues par ligne, reliquats,
  pas de réception au-delà du reste à recevoir.
- `GET /purchasing/orders/{id}/pdf` : bon de commande généré à la volée (reportlab).

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
