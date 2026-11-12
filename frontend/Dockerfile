# Image du frontend : on compile l'application React, puis on ne garde que les
# fichiers statiques (HTML, JS, CSS), servis par un petit Caddy.

# Étape 1 : compilation avec Node (jetée à la fin).
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Version affichée dans l'interface, fournie par le workflow de release.
ARG APP_VERSION=dev
ENV VITE_APP_VERSION=${APP_VERSION}
RUN npm run build

# Étape 2 : serveur de fichiers statiques.
FROM caddy:2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
