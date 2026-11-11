#!/usr/bin/env bash
# Ajoute un appareil au VPN : sudo ./add-client.sh pc-jeremy
# Affiche la config et un QR code (pour l'appli WireGuard sur téléphone).
set -euo pipefail
NAME=${1:?Usage: $0 <nom-appareil>}
# Adresse publique du VPN : variable WG_ENDPOINT, sinon fichier /etc/wireguard/endpoint (hors dépôt)
ENDPOINT=${WG_ENDPOINT:-$(cat /etc/wireguard/endpoint 2>/dev/null || true)}
if [[ -z "$ENDPOINT" ]]; then
  echo "Adresse du VPN inconnue. Enregistre-la une fois pour toutes :"
  echo '  echo "server.<domaine>:51820" | sudo tee /etc/wireguard/endpoint'
  exit 1
fi
DIR=/etc/wireguard/clients
if [[ ! -f /etc/wireguard/server.pub ]] || ! grep -q '^\[Interface\]' /etc/wireguard/wg0.conf 2>/dev/null; then
  echo "Serveur WireGuard non installé : lance d'abord sudo ./setup-server.sh"; exit 1
fi
mkdir -p "$DIR" && chmod 700 "$DIR"
[[ -f "$DIR/$NAME.conf" ]] && { echo "Le client $NAME existe déjà : $DIR/$NAME.conf"; exit 1; }

# Prochaine IP libre dans 10.8.0.0/24
last=$(grep -oP 'AllowedIPs = 10\.8\.0\.\K[0-9]+' /etc/wireguard/wg0.conf | sort -n | tail -1 || true)
IP="10.8.0.$(( ${last:-1} + 1 ))"

umask 077
priv=$(wg genkey); pub=$(echo "$priv" | wg pubkey); psk=$(wg genpsk)

cat >> /etc/wireguard/wg0.conf <<CONF

[Peer]
# $NAME
PublicKey = $pub
PresharedKey = $psk
AllowedIPs = $IP/32
CONF

cat > "$DIR/$NAME.conf" <<CONF
[Interface]
PrivateKey = $priv
Address = $IP/32

[Peer]
PublicKey = $(cat /etc/wireguard/server.pub)
PresharedKey = $psk
Endpoint = $ENDPOINT
AllowedIPs = 10.8.0.0/24
PersistentKeepalive = 25
CONF

# Recharge sans couper les connexions existantes
wg syncconf wg0 <(wg-quick strip wg0)

echo "Client $NAME -> $IP  (config : $DIR/$NAME.conf)"
qrencode -t ansiutf8 < "$DIR/$NAME.conf"
