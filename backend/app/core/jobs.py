"""Envoi de tâches de fond au worker ARQ (via Redis).

Les tâches sont des fonctions SYNCHRONES ordinaires, déclarées dans un registre :
- l'API appelle `enqueue("nom", arg1, arg2)` ;
- le worker (app/workers/main.py) exécute la fonction dans un thread ;
- avec JOBS_INLINE=true (tests, dev sans worker), la fonction s'exécute tout de suite.

Ainsi le code métier ne dépend ni d'ARQ ni de Redis, et se teste sans eux.
"""

import asyncio
import logging
from collections.abc import Callable

from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings

log = logging.getLogger(__name__)

JOBS: dict[str, Callable[..., object]] = {}


def job(name: str) -> Callable[[Callable[..., object]], Callable[..., object]]:
    """Décorateur : enregistre une fonction comme tâche de fond sous ce nom."""

    def register(fn: Callable[..., object]) -> Callable[..., object]:
        JOBS[name] = fn
        return fn

    return register


async def _enqueue(name: str, args: tuple) -> None:
    redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        await redis.enqueue_job("run_registered_job", name, *args)
    finally:
        await redis.aclose()


def enqueue(name: str, *args: object) -> None:
    if name not in JOBS:
        raise KeyError(f"Tâche inconnue : {name}")
    if get_settings().jobs_inline:
        JOBS[name](*args)
        return
    # Les routes synchrones de FastAPI tournent dans un thread sans boucle asyncio :
    # asyncio.run peut y créer la sienne le temps d'envoyer la tâche à Redis.
    asyncio.run(_enqueue(name, args))
