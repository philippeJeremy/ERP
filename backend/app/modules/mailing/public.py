"""Interface publique du module mailing : les modules métier préparent et envoient
leurs documents par mail avec `draft()` puis `queue()`."""

from app.modules.mailing.schemas import EmailDraft, EmailSend
from app.modules.mailing.service import MailError, draft, queue
from app.modules.mailing.templates import euros, fdate

__all__ = ["EmailDraft", "EmailSend", "MailError", "draft", "euros", "fdate", "queue"]
