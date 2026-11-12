#!/usr/bin/env bash
# Pare-feu du serveur : sudo LAN_SUBNET=192.168.1.0/24 ./ufw.sh
# - Internet : seul le port WireGuard est ouvert
# - VPN (wg0) : HTTP/HTTPS pour tous les appareils, SSH pour la plage admin uniquement (10.8.0.0/28)
# - LAN : SSH conservé tant que tu n'as pas validé l'accès par le VPN (évite de t'enfermer dehors)
set -euo pipefail
LAN_SUBNET=${LAN_SUBNET:?Indique ton réseau local, ex : LAN_SUBNET=192.168.1.0/24}
WG_PORT=51820
ADMIN_RANGE=10.8.0.0/28   # 10.8.0.1 à 10.8.0.15 : appareils créés avec le rôle admin

command -v ufw >/dev/null || apt-get install -y ufw

ufw --force reset
ufw default deny incoming
ufw default allow outgoing

ufw allow ${WG_PORT}/udp comment 'WireGuard'
ufw allow in on wg0 from "$ADMIN_RANGE" to any port 22 proto tcp comment 'SSH via VPN (admins)'
ufw allow in on wg0 to any port 80,443 proto tcp comment 'ERP via VPN'
ufw allow from "$LAN_SUBNET" to any port 22 proto tcp comment 'SSH LAN (temporaire)'

ufw --force enable
ufw status verbose

cat <<MSG

RAPPEL : Docker contourne ufw. Dans docker-compose.yml, publie les ports de Caddy
sur l'IP VPN uniquement ("10.8.0.1:443:443") et ne publie AUCUN port pour PostgreSQL.
Une fois le SSH via VPN testé, retire l'accès LAN : sudo ufw delete allow from $LAN_SUBNET to any port 22 proto tcp
MSG
