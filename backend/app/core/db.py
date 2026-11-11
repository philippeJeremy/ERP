"""Connexion à PostgreSQL et « contexte » de la transaction.

Le contexte (utilisateur courant, société courante) est transmis à PostgreSQL avec
`set_config(..., true)`, l'équivalent de `SET LOCAL` : la valeur ne vit que le temps
de la transaction. PostgreSQL s'en sert pour :
  - la Row-Level Security : chaque requête ne voit que les lignes de la société courante ;
  - le journal d'audit : les triggers savent QUI a modifié la ligne ;
  - les valeurs par défaut `company_id`, `created_by`, `updated_by`.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,  # vérifie qu'une connexion du pool est encore vivante avant usage
    pool_size=10,
    max_overflow=10,
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

_SET_CONTEXT = text(
    "SELECT set_config('app.user_id', :user_id, true),"
    "       set_config('app.company_id', :company_id, true)"
)


def _context_params(session: Session) -> dict[str, str] | None:
    ctx = session.info.get("db_context")
    if ctx is None:
        return None
    user_id, company_id = ctx
    return {
        "user_id": "" if user_id is None else str(user_id),
        "company_id": "" if company_id is None else str(company_id),
    }


@event.listens_for(SessionLocal, "after_begin")
def _apply_context_on_begin(session: Session, transaction, connection) -> None:
    """Réapplique le contexte au début de CHAQUE transaction.

    Indispensable : après un `commit()`, `SET LOCAL` est oublié. Sans ce hook, une
    deuxième transaction dans la même requête tournerait sans société ni utilisateur.
    """
    params = _context_params(session)
    if params is not None:
        connection.execute(_SET_CONTEXT, params)


def set_db_context(session: Session, *, user_id: int | None, company_id: int | None) -> None:
    """Fixe l'utilisateur et la société pour la session (et la transaction en cours)."""
    session.info["db_context"] = (user_id, company_id)
    if session.in_transaction():
        session.execute(_SET_CONTEXT, _context_params(session))


def get_db() -> Iterator[Session]:
    """Dépendance FastAPI : une session par requête.

    Les services appellent eux-mêmes `commit()` à la fin d'une opération d'écriture.
    Ici on garantit seulement le `rollback` en cas d'erreur et la fermeture.
    """
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
