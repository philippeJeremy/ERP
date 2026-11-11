"""Erreurs métier et leur traduction en réponses HTTP.

Les services lèvent des erreurs métier (NotFound, Conflict…) sans rien savoir de HTTP ;
un seul gestionnaire les convertit en JSON : {"error": {"code": ..., "message": ...}}.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm.exc import StaleDataError


class DomainError(Exception):
    status_code = 400
    code = "erreur_metier"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFound(DomainError):
    status_code = 404
    code = "introuvable"


class Conflict(DomainError):
    status_code = 409
    code = "conflit"


class Forbidden(DomainError):
    status_code = 403
    code = "interdit"


class Unauthorized(DomainError):
    status_code = 401
    code = "non_authentifie"


def _body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if isinstance(exc, Unauthorized) else None
        return JSONResponse(_body(exc.code, exc.message), exc.status_code, headers=headers)

    @app.exception_handler(StaleDataError)
    async def _stale(_: Request, __: StaleDataError) -> JSONResponse:
        # Verrouillage optimiste : quelqu'un a modifié la ligne entre la lecture et l'écriture.
        return JSONResponse(
            _body(
                "modifie_entre_temps",
                "Cet enregistrement a été modifié par quelqu'un "
                "d'autre. Rechargez-le avant de réessayer.",
            ),
            409,
        )
