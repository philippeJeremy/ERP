"""Routes HTTP du module mailing : réglages, modèles, historique."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.core.db import get_db
from app.modules.auth.public import require
from app.modules.mailing import service
from app.modules.mailing.schemas import (
    Kind,
    MessagePage,
    MessageRead,
    SmtpIn,
    SmtpRead,
    TemplateIn,
    TemplateRead,
    TestMail,
)

router = APIRouter(prefix="/mail", tags=["Messagerie"])

SETTINGS = Depends(require("mail:settings"))
READ = Depends(require("mail:read"))


@router.get("/smtp", response_model=SmtpRead, dependencies=[SETTINGS])
def read_smtp(db: Session = Depends(get_db)):
    """Réglages du serveur d'envoi (le mot de passe n'est jamais renvoyé)."""
    return service.read_smtp(db)


@router.put("/smtp", response_model=SmtpRead, dependencies=[SETTINGS])
def save_smtp(data: SmtpIn, db: Session = Depends(get_db)):
    return service.save_smtp(db, data)


@router.post("/smtp/test", response_model=MessageRead)
def test_smtp(data: TestMail, db: Session = Depends(get_db), ctx: RequestContext = SETTINGS):
    """Envoie un mail d'essai tout de suite et renvoie l'erreur éventuelle."""
    return service.send_test(db, ctx, str(data.to))


@router.get("/templates", response_model=list[TemplateRead], dependencies=[SETTINGS])
def list_templates(db: Session = Depends(get_db)):
    return service.list_templates(db)


@router.put("/templates/{kind}", response_model=TemplateRead, dependencies=[SETTINGS])
def save_template(kind: Kind, data: TemplateIn, db: Session = Depends(get_db)):
    return service.save_template(db, kind, data)


@router.delete("/templates/{kind}", response_model=TemplateRead, dependencies=[SETTINGS])
def reset_template(kind: Kind, db: Session = Depends(get_db)):
    """Revient au modèle par défaut."""
    return service.reset_template(db, kind)


@router.get("/messages", response_model=MessagePage, dependencies=[READ])
def list_messages(
    status: Literal["en_attente", "envoye", "echec"] | None = None,
    document_type: str | None = Query(None, max_length=30),
    document_id: int | None = None,
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return service.list_messages(
        db, status=status, document_type=document_type, document_id=document_id,
        limit=limit, offset=offset,
    )  # fmt: skip


@router.post("/messages/{message_id}/retry", response_model=MessageRead)
def retry(message_id: int, db: Session = Depends(get_db), ctx: RequestContext = READ):
    return service.retry(db, ctx, message_id)


@router.get("/messages/{message_id}/attachments/{index}", dependencies=[READ])
def attachment(message_id: int, index: int, db: Session = Depends(get_db)):
    """La pièce jointe telle qu'elle est partie."""
    a = service.get_attachment(db, message_id, index)
    return Response(
        a.content,
        media_type=a.content_type,
        headers={"Content-Disposition": f'inline; filename="{a.filename}"'},
    )
