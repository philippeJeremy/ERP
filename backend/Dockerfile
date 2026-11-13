# Image unique pour l'API, le worker et le job de migration :
# seule la commande change (voir docker-compose.yaml).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# Polices embarquées dans les PDF (factures Factur-X / PDF/A : polices incluses obligatoires).
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# 1) Dépendances d'abord : cette couche reste en cache tant que pyproject.toml ne change pas.
COPY pyproject.toml ./
#    On installe seulement les dépendances listées dans pyproject.toml, pas le projet lui-même
#    (le code est lu directement depuis /app grâce à PYTHONPATH).
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt

# Version de l'application, fournie par le workflow de release (tag Git vX.Y.Z).
# Visible dans /health : on sait toujours quelle version tourne.
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

# 2) Puis le code.
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# Utilisateur sans privilèges : si l'API est compromise, l'attaquant n'est pas root.
RUN useradd --create-home --uid 10001 erp
USER erp

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
