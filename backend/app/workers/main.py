"""Worker de tâches de fond (ARQ + Redis), dans un conteneur séparé de l'API.

Lancement : arq app.workers.main.WorkerSettings
Les vraies tâches (PDF de factures, exports, e-mails) viendront avec les modules.
"""

import asyncio
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


async def run_registered_job(ctx: dict, name: str, *args: object) -> object:
    """Exécute une tâche du registre (app/core/jobs.py) dans un thread : le code métier
    est synchrone (SQLAlchemy sync) et ne doit pas bloquer la boucle du worker."""
    from app.core.jobs import JOBS

    log.info("tâche %s %s", name, args)
    return await asyncio.to_thread(JOBS[name], *args)


async def startup(ctx: dict) -> None:
    setup_logging(get_settings().log_level)
    modules.load_models()
    modules.load_jobs()
    log.info("worker démarré")


async def poll_import_sources(ctx: dict) -> int:
    """Relèves automatiques des tarifs fournisseurs dont l'heure est venue."""
    from app.core.jobs import JOBS

    return await asyncio.to_thread(JOBS["catalog.poll_due_sources"])


class WorkerSettings:
    functions = [ping, run_registered_job]
    cron_jobs = [
        cron(purge_sessions, hour=3, minute=17),  # heure UTC
        # Toutes les 5 minutes ; chaque relève a sa propre fréquence (next_check_at).
        cron(poll_import_sources, minute=set(range(0, 60, 5)), unique=True, timeout=1800),
    ]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
