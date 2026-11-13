"""Règles du module mailing : réglages SMTP, modèles, préparation et envoi des mails."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import secrets
from app.core.context import RequestContext
from app.core.db import SessionLocal, set_db_context
from app.core.errors import DomainError, NotFound
from app.core.jobs import enqueue
from app.modules.auth.public import user_full_name
from app.modules.mailing import sender, templates
from app.modules.mailing.models import Attachment, MailTemplate, Message, SmtpSettings
from app.modules.mailing.schemas import (
    AttachmentRead,
    EmailDraft,
    EmailSend,
    MessagePage,
    MessageRead,
    SmtpIn,
    SmtpRead,
    Suggestion,
    TemplateIn,
    TemplateRead,
)
from app.modules.org import public as org


class MailError(DomainError):
    status_code = 422
    code = "mail_impossible"


def now() -> datetime:
    return datetime.now(UTC)


# --- Réglages SMTP ----------------------------------------------------------------------


def _smtp(db: Session) -> SmtpSettings | None:
    return db.scalar(select(SmtpSettings))


def read_smtp(db: Session) -> SmtpRead:
    s = _smtp(db)
    if s is None:
        return SmtpRead(
            configured=False, enabled=False, host=None, port=587, security="starttls",
            username=None, has_password=False, from_email=None, from_name=None,
            reply_to=None, bcc=None,
        )  # fmt: skip
    return SmtpRead(
        configured=True, enabled=s.enabled, host=s.host, port=s.port, security=s.security,
        username=s.username, has_password=bool(s.password_encrypted), from_email=s.from_email,
        from_name=s.from_name, reply_to=s.reply_to, bcc=s.bcc,
    )  # fmt: skip


def save_smtp(db: Session, data: SmtpIn) -> SmtpRead:
    s = _smtp(db)
    if s is None:
        s = SmtpSettings()
        db.add(s)
    for field in ("enabled", "host", "port", "security", "username", "from_email", "from_name",
                  "reply_to", "bcc"):  # fmt: skip
        setattr(s, field, getattr(data, field))
    if data.password:
        s.password_encrypted = secrets.encrypt(data.password)
    if not data.username:
        s.password_encrypted = None
    s.updated_at = now()
    db.commit()
    return read_smtp(db)


def smtp_ready(db: Session) -> bool:
    s = _smtp(db)
    return bool(s and s.enabled)


def _deliver(s: SmtpSettings, message: Message) -> None:
    to = [x for x in message.to_addrs.split(",") if x]
    cc = [x for x in (message.cc_addrs or "").split(",") if x]
    bcc = [x for x in (message.bcc_addrs or "").split(",") if x]
    email = sender.build(
        from_email=s.from_email, from_name=s.from_name, to=to, cc=cc, reply_to=message.reply_to,
        subject=message.subject, body=message.body,
        attachments=[(a.filename, a.content_type, a.content) for a in message.attachments],
    )  # fmt: skip
    password = secrets.decrypt(s.password_encrypted) if s.password_encrypted else None
    sender.deliver(
        host=s.host, port=s.port, security=s.security, username=s.username, password=password,
        message=email, recipients=to + cc + bcc,
    )  # fmt: skip


def send_test(db: Session, ctx: RequestContext, to: str) -> MessageRead:
    """Mail d'essai, envoyé tout de suite (on veut voir l'erreur éventuelle à l'écran)."""
    s = _smtp(db)
    if s is None:
        raise MailError("Enregistrez d'abord les réglages du serveur d'envoi")
    company = org.get_company(db, ctx.company_id)
    message = Message(
        kind="test", from_addr=s.from_email, to_addrs=to, reply_to=s.reply_to,
        subject=f"Test d'envoi — {company.name}",
        body="Ce message confirme que l'ERP peut envoyer des mails avec ces réglages.",
        created_by=ctx.user_id, attempts=1,
    )  # fmt: skip
    db.add(message)
    try:
        _deliver(s, message)
    except sender.SendError as exc:
        message.status, message.error = "echec", str(exc)
        db.commit()
        raise MailError(str(exc)) from exc
    message.status, message.sent_at = "envoye", now()
    db.commit()
    return message_read(message)


# --- Modèles ----------------------------------------------------------------------------


def _template(db: Session, kind: str) -> tuple[str, str, bool]:
    row = db.scalar(select(MailTemplate).where(MailTemplate.kind == kind))
    if row is not None:
        return row.subject, row.body, True
    subject, body = templates.DEFAULTS[kind]
    return subject, body, False


def list_templates(db: Session) -> list[TemplateRead]:
    result = []
    for kind, label in templates.LABELS.items():
        subject, body, customized = _template(db, kind)
        result.append(
            TemplateRead(
                kind=kind,
                label=label,
                subject=subject,
                body=body,
                customized=customized,
                fields=templates.FIELDS[kind],
            )  # fmt: skip
        )
    return result


def save_template(db: Session, kind: str, data: TemplateIn) -> TemplateRead:
    row = db.scalar(select(MailTemplate).where(MailTemplate.kind == kind))
    if row is None:
        row = MailTemplate(kind=kind)
        db.add(row)
    row.subject, row.body = data.subject, data.body
    db.commit()
    return next(t for t in list_templates(db) if t.kind == kind)


def reset_template(db: Session, kind: str) -> TemplateRead:
    row = db.scalar(select(MailTemplate).where(MailTemplate.kind == kind))
    if row is not None:
        db.delete(row)
        db.commit()
    return next(t for t in list_templates(db) if t.kind == kind)


# --- Brouillon et envoi d'un document ---------------------------------------------------


def message_read(m: Message) -> MessageRead:
    return MessageRead(
        id=m.id, kind=m.kind, document_type=m.document_type, document_id=m.document_id,
        document_number=m.document_number, to_addrs=m.to_addrs, cc_addrs=m.cc_addrs,
        subject=m.subject, body=m.body, status=m.status, error=m.error, attempts=m.attempts,
        created_at=m.created_at, sent_at=m.sent_at,
        attachments=[AttachmentRead(filename=a.filename, size=len(a.content)) for a in m.attachments],  # noqa: E501
    )  # fmt: skip


def history(db: Session, document_type: str, document_id: int) -> list[MessageRead]:
    rows = db.scalars(
        select(Message)
        .where(Message.document_type == document_type, Message.document_id == document_id)
        .order_by(Message.id.desc())
    )
    return [message_read(m) for m in rows]


def draft(
    db: Session,
    ctx: RequestContext,
    *,
    kind: str,
    values: dict[str, str],
    to: list[str],
    suggestions: list[tuple[str, str]],
    attachments: list[str],
    document_type: str,
    document_id: int,
) -> EmailDraft:
    """Le message pré-rempli : modèle de la société + valeurs du document."""
    company = org.get_company(db, ctx.company_id)
    values = {"societe": company.name, "signature": user_full_name(db, ctx.user_id) or "", **values}
    subject, body, _ = _template(db, kind)
    seen: set[str] = set()
    unique = []
    for label, email in suggestions:
        if email and email.lower() not in seen:
            seen.add(email.lower())
            unique.append(Suggestion(label=label, email=email))
    return EmailDraft(
        to=[x for x in to if x], cc=[], subject=templates.render(subject, values),
        body=templates.render(body, values), attachments=attachments, suggestions=unique,
        smtp_ready=smtp_ready(db), history=history(db, document_type, document_id),
    )  # fmt: skip


def queue(
    db: Session,
    ctx: RequestContext,
    *,
    kind: str,
    data: EmailSend,
    attachments: list[tuple[str, str, bytes]],
    document_type: str,
    document_id: int,
    document_number: str | None,
    partner_id: int | None,
) -> Message:
    """Enregistre le mail (avec les changements faits par l'appelant dans la même
    transaction), valide, puis confie l'envoi au worker."""
    s = _smtp(db)
    if s is None or not s.enabled:
        raise MailError(
            "L'envoi de mails n'est pas configuré pour cette société (Administration → Messagerie)"
        )
    message = Message(
        kind=kind, document_type=document_type, document_id=document_id,
        document_number=document_number, partner_id=partner_id, from_addr=s.from_email,
        to_addrs=",".join(data.to), cc_addrs=",".join(data.cc) or None, bcc_addrs=s.bcc,
        reply_to=s.reply_to, subject=data.subject, body=data.body, created_by=ctx.user_id,
    )  # fmt: skip
    for filename, content_type, content in attachments:
        message.attachments.append(
            Attachment(filename=filename, content_type=content_type, content=content)
        )
    db.add(message)
    db.commit()
    enqueue("mailing.send", ctx.company_id, message.id, ctx.user_id)
    db.refresh(message)
    return message


def send_job(company_id: int, message_id: int, user_id: int | None = None) -> None:
    """Tâche de fond : envoie le mail et note le résultat (envoyé ou échec + raison)."""
    with SessionLocal() as db:
        set_db_context(db, user_id=user_id, company_id=company_id)
        message = db.scalar(select(Message).where(Message.id == message_id).with_for_update())
        if message is None or message.status == "envoye":
            return
        message.attempts += 1
        s = _smtp(db)
        try:
            if s is None or not s.enabled:
                raise sender.SendError("Envoi de mails désactivé pour cette société")
            _deliver(s, message)
        except sender.SendError as exc:
            message.status, message.error = "echec", str(exc)
        except Exception as exc:  # erreur inattendue : notée, pas de plantage du worker
            message.status, message.error = "echec", f"Erreur inattendue : {type(exc).__name__}"
        else:
            message.status, message.error, message.sent_at = "envoye", None, now()
        db.commit()


def retry(db: Session, ctx: RequestContext, message_id: int) -> MessageRead:
    message = db.get(Message, message_id)
    if message is None:
        raise NotFound("Mail introuvable")
    if message.status != "echec":
        raise MailError("Seul un envoi en échec se relance")
    message.status = "en_attente"
    db.commit()
    enqueue("mailing.send", ctx.company_id, message.id, ctx.user_id)
    db.refresh(message)
    return message_read(message)


def list_messages(
    db: Session, *, status: str | None, document_type: str | None, document_id: int | None,
    limit: int, offset: int,
) -> MessagePage:  # fmt: skip
    query = select(Message)
    if status:
        query = query.where(Message.status == status)
    if document_type:
        query = query.where(Message.document_type == document_type)
    if document_id is not None:
        query = query.where(Message.document_id == document_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(Message.id.desc()).limit(limit).offset(offset))
    return MessagePage(items=[message_read(m) for m in rows], total=total)


def get_attachment(db: Session, message_id: int, index: int) -> Attachment:
    message = db.get(Message, message_id)
    if message is None or index >= len(message.attachments):
        raise NotFound("Pièce jointe introuvable")
    return message.attachments[index]
