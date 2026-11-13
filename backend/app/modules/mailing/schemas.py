"""Schémas du module mailing."""

from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field

from app.shared.schemas import Schema

Kind = Literal["devis", "facture", "avoir", "relance", "commande_fournisseur"]


class SmtpIn(Schema):
    enabled: bool = True
    host: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.-]+$")
    port: int = Field(587, ge=1, le=65535)
    security: Literal["starttls", "ssl", "none"] = "starttls"
    username: str | None = Field(None, max_length=254)
    password: str | None = Field(None, max_length=500)  # vide = inchangé
    from_email: EmailStr
    from_name: str | None = Field(None, max_length=100)
    reply_to: EmailStr | None = None
    bcc: EmailStr | None = None


class SmtpRead(Schema):
    configured: bool
    enabled: bool
    host: str | None
    port: int
    security: str
    username: str | None
    has_password: bool
    from_email: str | None
    from_name: str | None
    reply_to: str | None
    bcc: str | None


class TestMail(Schema):
    to: EmailStr


class TemplateIn(Schema):
    subject: str = Field(min_length=1, max_length=250)
    body: str = Field(min_length=1, max_length=10000)


class TemplateRead(Schema):
    kind: str
    label: str
    subject: str
    body: str
    customized: bool
    fields: list[str]  # champs utilisables : {numero}, {montant}…


class AttachmentRead(Schema):
    filename: str
    size: int


class MessageRead(Schema):
    id: int
    kind: str
    document_type: str | None
    document_id: int | None
    document_number: str | None
    to_addrs: str
    cc_addrs: str | None
    subject: str
    body: str
    status: str
    error: str | None
    attempts: int
    created_at: datetime
    sent_at: datetime | None
    attachments: list[AttachmentRead]


class MessagePage(Schema):
    items: list[MessageRead]
    total: int


class Suggestion(Schema):
    label: str
    email: str


class EmailDraft(Schema):
    """Ce que la fenêtre d'envoi propose (modifiable avant l'envoi)."""

    to: list[str]
    cc: list[str]
    subject: str
    body: str
    attachments: list[str]
    suggestions: list[Suggestion]
    smtp_ready: bool
    history: list[MessageRead]


class EmailSend(Schema):
    to: list[EmailStr] = Field(min_length=1, max_length=20)
    cc: list[EmailStr] = Field(default_factory=list, max_length=20)
    subject: str = Field(min_length=1, max_length=250)
    body: str = Field(min_length=1, max_length=20000)
