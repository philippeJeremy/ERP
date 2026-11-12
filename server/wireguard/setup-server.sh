#!/usr/bin/env bash
# Installe WireGuard sur le serveur (à lancer une seule fois) : sudo ./setup-server.sh
# Réseau VPN : 10.8.0.0/24 — serveur = 10.8.0.1. Les clients n'accèdent qu'au serveur (pas au reste du LAN).
set -euo pipefail
WG_PORT=51820

apt-get update && apt-get install -y wireguard qrencode

if [[ -f /etc/wireguard/wg0.conf ]] && ! grep -q '^\[Interface\]' /etc/wireguard/wg0.conf; then
  echo "/etc/wireguard/wg0.conf existe mais est incomplet (pas de [Interface]) : supprime-le puis relance."; exit 1
fi
if [[ ! -f /etc/wireguard/wg0.conf ]]; then
  umask 077
  wg genkey | tee /etc/wireguard/server.key | wg pubkey > /etc/wireguard/server.pub
  cat > /etc/wireguard/wg0.conf <<CONF
[Interface]
Address = 10.8.0.1/24
ListenPort = ${WG_PORT}
PrivateKey = $(cat /etc/wireguard/server.key)
CONF
  echo "wg0.conf créé."
else
  echo "wg0.conf existe déjà, conservé."
fi

systemctl enable --now wg-quick@wg0

# Docker doit démarrer APRÈS wg0 : Caddy écoute sur 10.8.0.1, qui n'existe qu'une fois le VPN monté.
mkdir -p /etc/systemd/system/docker.service.d
cat > /etc/systemd/system/docker.service.d/after-wireguard.conf <<CONF
[Unit]
After=wg-quick@wg0.service
Wants=wg-quick@wg0.service
CONF
systemctl daemon-reload

echo "OK. Pense à rediriger le port UDP ${WG_PORT} de la box vers ce serveur."
echo "Ajoute un appareil avec : sudo ./add-client.sh <nom>"
