#!/usr/bin/env bash
# Déploie une version publiée de l'ERP sur ce serveur.
#
#   ./server/deploy.sh 0.1.0
#
# Étapes :
#   1. place le dépôt sur le tag v0.1.0 (docker-compose.yaml et script d'init
#      correspondent exactement à cette version) ;
#   2. écrit ERP_VERSION=0.1.0 dans .env ;
#   3. télécharge les images 0.1.0 depuis ghcr.io ;
#   4. redémarre les services : le job « migrate » applique les migrations
#      AVANT que la nouvelle API démarre.
#
# Revenir en arrière = redéployer la version précédente. ATTENTION : les
# migrations, elles, ne sont pas annulées automatiquement. Si la nouvelle version
# modifiait la base, faire une sauvegarde (pg_dump) avant de déployer.
set -euo pipefail

VERSION="${1:-}"
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Usage : $0 <version>   (ex. $0 0.1.0)" >&2
    exit 1
fi

cd "$(dirname "$0")/.."   # racine du dépôt

if [[ ! -f .env ]]; then
    echo "Fichier .env absent : le créer à partir de .env.example." >&2
    exit 1
fi
if [[ -f docker-compose.override.yaml ]]; then
    echo "docker-compose.override.yaml présent : c'est la config de DEV, à supprimer sur le serveur." >&2
    exit 1
fi

echo "==> Récupération du tag v$VERSION"
git fetch --tags --quiet
git -c advice.detachedHead=false checkout --quiet "v$VERSION"

echo "==> ERP_VERSION=$VERSION dans .env"
if grep -q '^ERP_VERSION=' .env; then
    sed -i "s/^ERP_VERSION=.*/ERP_VERSION=$VERSION/" .env
else
    echo "ERP_VERSION=$VERSION" >> .env
fi

echo "==> Téléchargement des images"
docker compose pull

echo "==> Démarrage (migrations d'abord)"
docker compose up -d --remove-orphans

echo "==> Attente de l'API (healthcheck /ready)"
for _ in $(seq 1 60); do
    health="$(docker compose ps api --format '{{.Health}}' 2>/dev/null || true)"
    [[ "$health" == "healthy" ]] && break
    sleep 2
done
if [[ "$health" != "healthy" ]]; then
    echo "L'API n'est pas saine (état : ${health:-inconnu}). Voir : docker compose logs migrate api" >&2
    exit 1
fi

echo "==> Nettoyage des anciennes images"
docker image prune -f > /dev/null

docker compose ps
echo "Version $VERSION déployée."
