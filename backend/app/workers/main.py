"""Worker de tâches de fond (ARQ + Redis), dans un conteneur séparé de l'API.

Lancement : arq app.workers.main.WorkerSettings
Les vraies tâches (PDF de factures, exports, e-mails) viendront avec les modules.
"""

import logging

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import setup_logging

log = logging.getLogger(__name__)


async def ping(ctx: dict) -> str:
    """Tâche de test : vérifie que la chaîne API → Redis → worker fonctionne."""
    log.info("ping reçu")
    return "pong"


async def startup(ctx: dict) -> None:
    setup_logging(get_settings().log_level)
    log.info("worker démarré")


class WorkerSettings:
    functions = [ping]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
