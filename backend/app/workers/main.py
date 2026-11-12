"""Worker de tâches de fond (ARQ + Redis), dans un conteneur séparé de l'API.

Lancement : arq app.workers.main.WorkerSettings
Les vraies tâches (PDF de factures, exports, e-mails) viendront avec les modules.
"""

import logging

from arq import cron
from arq.connections import RedisSettings

from app import modules
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import setup_logging

log = logging.getLogger(__name__)


async def ping(ctx: dict) -> str:
    """Tâche de test : vérifie que la chaîne API → Redis → worker fonctionne."""
    log.info("ping reçu")
    return "pong"


async def purge_sessions(ctx: dict) -> int:
    """Chaque nuit : supprime les sessions (refresh tokens) expirées depuis 30 jours."""
    from app.modules.auth.public import purge_expired_refresh_tokens

    with SessionLocal() as db:
        count = purge_expired_refresh_tokens(db)
    log.info("sessions expirées supprimées : %s", count)
    return count


async def startup(ctx: dict) -> None:
    setup_logging(get_settings().log_level)
    modules.load_models()
    log.info("worker démarré")


class WorkerSettings:
    functions = [ping]
    cron_jobs = [cron(purge_sessions, hour=3, minute=17)]  # heure UTC
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
