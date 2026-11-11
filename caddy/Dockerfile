# Caddy officiel + module caddy-dns/ovh, compilé avec xcaddy.
#
# Le module permet le challenge ACME « DNS-01 » : pour prouver à Let's Encrypt que
# le domaine nous appartient, Caddy crée un enregistrement TXT temporaire via l'API
# OVH. Aucun port n'a besoin d'être ouvert sur Internet : indispensable ici, car le
# site n'est joignable que par le VPN.

# Étape 1 : compilation (image lourde, avec Go), jetée à la fin.
FROM caddy:2-builder AS builder
RUN xcaddy build --with github.com/caddy-dns/ovh

# Étape 2 : image finale légère, avec seulement le binaire compilé.
FROM caddy:2-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
COPY Caddyfile /etc/caddy/Caddyfile

ARG APP_VERSION=dev
LABEL org.opencontainers.image.description="Reverse proxy de l'ERP (Caddy + DNS OVH)"
ENV ERP_VERSION=${APP_VERSION}
