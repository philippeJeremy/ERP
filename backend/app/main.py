"""Point d'entrée de l'API."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import modules
from app.core.config import get_settings
from app.core.db import engine
from app.core.errors import register_error_handlers
from app.core.logging import setup_logging

settings = get_settings()
setup_logging(settings.log_level)
modules.load_models()

app = FastAPI(
    title="ERP",
    version="0.1.0",
    root_path=settings.root_path,
    # Pas de documentation interactive exposée en production.
    docs_url=None if settings.environment == "prod" else "/docs",
    redoc_url=None,
)
register_error_handlers(app)

for router in modules.routers():
    app.include_router(router)


@app.get("/health", tags=["Supervision"])
def health():
    """Liveness : le processus répond. Si KO, Kubernetes redémarre le conteneur."""
    return {"status": "ok"}


@app.get("/ready", tags=["Supervision"])
def ready():
    """Readiness : l'API peut servir (base joignable). Si KO, on ne lui envoie plus de trafic."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return {"status": "ready"}
