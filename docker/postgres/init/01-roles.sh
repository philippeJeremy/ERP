#!/bin/sh
# Exécuté UNE SEULE FOIS par l'image postgres officielle, au premier démarrage
# (volume de données vide). Pour le rejouer : supprimer le volume (perte des données !).
#
# Crée deux rôles applicatifs, sur le principe du moindre privilège :
#   erp_owner : propriétaire de la base et des tables ; utilisé par les migrations.
#   erp_app   : utilisé par l'API ; lit/écrit les données, ne peut PAS modifier
#               la structure (pas de DROP/ALTER), et reste soumis à la RLS.
set -eu

: "${ERP_OWNER_PASSWORD:?ERP_OWNER_PASSWORD manquant}"
: "${ERP_APP_PASSWORD:?ERP_APP_PASSWORD manquant}"
ERP_DB="${ERP_DB:-erp}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
     -v owner_pw="$ERP_OWNER_PASSWORD" -v app_pw="$ERP_APP_PASSWORD" -v db="$ERP_DB" <<'EOSQL'
CREATE ROLE erp_owner LOGIN PASSWORD :'owner_pw';
CREATE ROLE erp_app   LOGIN PASSWORD :'app_pw';
CREATE DATABASE :"db" OWNER erp_owner ENCODING 'UTF8' TEMPLATE template0;
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE :"db" TO erp_app;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$ERP_DB" <<'EOSQL'
-- Personne d'autre que le propriétaire ne crée d'objets dans public.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
EOSQL

echo "Rôles erp_owner / erp_app et base $ERP_DB créés."
