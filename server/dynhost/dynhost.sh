#!/usr/bin/env bash
# Mise à jour DynHost OVH — version améliorée de l'ancien dynhost.sh
# Identifiants dans /etc/dynhost.env (chmod 600), une ligne par hôte :
#   HOSTS="server.<domaine>:<domaine>-ident:MOTDEPASSE monitor.<domaine>:<domaine>-moni:MOTDEPASSE"
set -euo pipefail
source /etc/dynhost.env

# IP publique avec service de secours, et contrôle du format
IP=$(curl -4 -sf --max-time 10 ifconfig.me || curl -4 -sf --max-time 10 api.ipify.org || true)
if [[ ! $IP =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  logger -t dynhost "IP publique introuvable, aucune mise à jour"
  exit 1
fi

for entry in $HOSTS; do
  IFS=: read -r host user pass <<< "$entry"
  # On n'appelle OVH que si l'IP a changé (évite d'être bloqué pour abus)
  # Interroge directement le serveur DNS OVH de la zone (pas de cache)
  ns=$(dig +short NS "${host#*.}" | head -n1)
  current=$(dig +short A "$host" ${ns:+@$ns} | tail -n1)
  if [[ "$current" == "$IP" ]]; then
    continue
  fi
  resp=$(curl -s --max-time 15 --user "$user:$pass" \
    "https://www.ovh.com/nic/update?system=dyndns&hostname=$host&myip=$IP")
  logger -t dynhost "$host : $current -> $IP ($resp)"
done
