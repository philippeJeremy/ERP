#!/usr/bin/env bash
# Installe le script DynHost : sudo ./install.sh  (dynhost.env doit être rempli à côté)
set -euo pipefail
apt-get install -y dnsutils curl
install -d /opt/dynhost
install -m 755 dynhost.sh /opt/dynhost/dynhost.sh
install -m 600 dynhost.env /etc/dynhost.env
# Toutes les 5 minutes, via /etc/cron.d (n'écrase pas la crontab root existante)
echo '*/5 * * * * root /opt/dynhost/dynhost.sh' > /etc/cron.d/dynhost
/opt/dynhost/dynhost.sh && echo "OK. Journal : journalctl -t dynhost"
