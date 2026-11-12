#!/usr/bin/env bash
# Ajoute un appareil au VPN : sudo ./add-client.sh <nom-appareil> [user|admin]
#   user  (défaut) : accès au site ERP uniquement        -> IP 10.8.0.16 à 10.8.0.254
#   admin          : accès au site ERP + SSH du serveur  -> IP 10.8.0.2  à 10.8.0.15
# Le pare-feu (ufw.sh) n'autorise le SSH que depuis la plage admin 10.8.0.0/28.
# Affiche la config et un QR code (pour l'appli WireGuard sur téléphone).
set -euo pipefail
NAME=${1:?Usage: $0 <nom-appareil> [user|admin]}
ROLE=${2:-user}
case "$ROLE" in
  admin) FIRST=2;  LAST=15 ;;
  user)  FIRST=16; LAST=254 ;;
  *) echo "Rôle inconnu : $ROLE (user ou admin)"; exit 1 ;;
esac
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

# Première IP libre dans la plage du rôle
used=$(grep -oP 'AllowedIPs = 10\.8\.0\.\K[0-9]+' /etc/wireguard/wg0.conf || true)
IP=""
for n in $(seq "$FIRST" "$LAST"); do
  if ! grep -qx "$n" <<< "$used"; then IP="10.8.0.$n"; break; fi
done
[[ -z "$IP" ]] && { echo "Plus d'adresse libre pour le rôle $ROLE"; exit 1; }

umask 077
priv=$(wg genkey); pub=$(echo "$priv" | wg pubkey); psk=$(wg genpsk)

cat >> /etc/wireguard/wg0.conf <<CONF

[Peer]
# $NAME ($ROLE)
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

echo "Client $NAME [$ROLE] -> $IP  (config : $DIR/$NAME.conf)"
qrencode -t ansiutf8 < "$DIR/$NAME.conf"
