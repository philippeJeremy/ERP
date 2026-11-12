# ERP

ERP modulaire et multi-société : FastAPI + PostgreSQL + Caddy, déployé avec Docker Compose
(prêt pour Kubernetes). Projet d'apprentissage.

| Dossier | Contenu |
|---|---|
| `backend/` | API FastAPI (voir `backend/README.md`) |
| `frontend/` | Interface React (voir `frontend/README.md`) |
| `caddy/` | Reverse proxy : image Caddy + module DNS OVH, `Caddyfile` |
| `docker/` | Scripts d'initialisation des conteneurs (rôles PostgreSQL) |
| `server/` | Ce qui s'installe sur l'hôte : WireGuard, ufw, DynHost, script de déploiement |
| `.github/workflows/` | CI (à chaque push) et Release (à chaque tag) |

## Développement (poste local)

```bash
cp .env.example .env                                       # puis remplir (ERP_VERSION=dev)
cp docker-compose.override.example.yaml docker-compose.override.yaml
docker compose up -d --build                               # API, base, worker (images locales)
cd frontend && npm install && npm run dev                  # interface
```
Interface : http://localhost:5173 — API : http://127.0.0.1:8000/docs
(Caddy et le conteneur frontend ne sont pas démarrés en local).

## Publier une version

Le numéro suit le [versionnage sémantique](https://semver.org/lang/fr/) `MAJEUR.MINEUR.CORRECTIF` :
correctif = bug corrigé, mineur = nouvelle fonctionnalité, majeur = changement incompatible.

```bash
git tag v0.1.0
git push origin v0.1.0
```

Le workflow **Release** relance la CI, construit les images, les publie sur
`ghcr.io/<propriétaire>/erp-backend` et `erp-caddy`, et crée la Release GitHub.

## Déployer une version (serveur)

```bash
./server/deploy.sh 0.1.0
```

Le script place le dépôt sur le tag, met `ERP_VERSION` à jour dans `.env`, télécharge
les images, applique les migrations puis redémarre l'application. Revenir en arrière
= redéployer la version précédente (les migrations ne sont pas annulées : sauvegarder
la base avant une mise à jour qui la modifie).

Premier déploiement uniquement, après `deploy.sh` :
```bash
docker compose run --rm api python -m app.cli bootstrap \
    --email <email> --name "<nom>" --company-code <CODE> --company-name "<raison sociale>"
```
