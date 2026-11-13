"""Schéma PostgreSQL `mail` : serveur d'envoi (SMTP) et modèles par société, et
journal des mails envoyés (avec leurs pièces jointes, telles qu'envoyées)."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models import CURRENT_COMPANY_ID, Base, BusinessEntity, CompanyScopedMixin, IdMixin

SECURITIES = ("starttls", "ssl", "none")
KINDS = ("devis", "facture", "avoir", "relance", "commande_fournisseur", "test")
STATUSES = ("en_attente", "envoye", "echec")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class SmtpSettings(Base):
    """Le serveur d'envoi d'une société. Le mot de passe est chiffré (SECRETS_KEY)."""

    __tablename__ = "smtp_settings"
    __table_args__ = (
        CheckConstraint(_in("security", SECURITIES), name="security"),
        CheckConstraint("port BETWEEN 1 AND 65535", name="port_range"),
        {"schema": "mail"},
    )

    company_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("org.companies.id"),
        primary_key=True,
        server_default=CURRENT_COMPANY_ID,
    )
    enabled: Mapped[bool] = mapped_column(server_default="false")
    host: Mapped[str] = mapped_column(String(253))
    port: Mapped[int] = mapped_column(server_default="587")
    security: Mapped[str] = mapped_column(String(10), server_default="starttls")
    username: Mapped[str | None] = mapped_column(String(254))
    password_encrypted: Mapped[str | None] = mapped_column(Text)
    from_email: Mapped[str] = mapped_column(String(254))
    from_name: Mapped[str | None] = mapped_column(String(100))
    reply_to: Mapped[str | None] = mapped_column(String(254))
    bcc: Mapped[str | None] = mapped_column(String(254))  # copie cachée d'archivage
    updated_at: Mapped[datetime | None]


class MailTemplate(Base, BusinessEntity, CompanyScopedMixin):
    """Modèle de message modifiable : objet et texte avec des champs {numero}, {montant}…"""

    __tablename__ = "templates"
    __table_args__ = (
        UniqueConstraint("company_id", "kind"),
        CheckConstraint(_in("kind", KINDS), name="kind"),
        {"schema": "mail"},
    )

    kind: Mapped[str] = mapped_column(String(30))
    subject: Mapped[str] = mapped_column(String(250))
    body: Mapped[str] = mapped_column(Text)


class Message(Base, IdMixin, CompanyScopedMixin):
    """Un mail envoyé (ou à envoyer) : ce qui est parti, à qui, quand, avec quel résultat."""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(_in("kind", KINDS), name="kind"),
        CheckConstraint(_in("status", STATUSES), name="status"),
        Index("ix_messages_document", "company_id", "document_type", "document_id"),
        {"schema": "mail"},
    )

    kind: Mapped[str] = mapped_column(String(30))
    document_type: Mapped[str | None] = mapped_column(String(30))  # quote, invoice…
    document_id: Mapped[int | None] = mapped_column(BigInteger)
    document_number: Mapped[str | None] = mapped_column(String(30))
    partner_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    from_addr: Mapped[str] = mapped_column(String(300))
    to_addrs: Mapped[str] = mapped_column(Text)  # séparés par des virgules
    cc_addrs: Mapped[str | None] = mapped_column(Text)
    bcc_addrs: Mapped[str | None] = mapped_column(Text)
    reply_to: Mapped[str | None] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(250))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), server_default="en_attente", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("auth.users.id"))
    sent_at: Mapped[datetime | None]

    attachments: Mapped[list["Attachment"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="Attachment.id"
    )


class Attachment(Base, IdMixin, CompanyScopedMixin):
    __tablename__ = "attachments"
    __table_args__ = {"schema": "mail"}

    message_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("mail.messages.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(100))
    content: Mapped[bytes] = mapped_column(LargeBinary)
