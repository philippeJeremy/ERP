"""Règles métier des relèves automatiques (configuration, test de connexion)."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import secrets
from app.core.config import get_settings
from app.core.context import RequestContext
from app.core.errors import Conflict, NotFound
from app.core.jobs import enqueue
from app.modules.catalog import repository as repo
from app.modules.catalog.models import ImportProfile, ImportSource, ImportSourceFile
from app.modules.catalog.poller import _seen, config_of
from app.modules.catalog.remote import Connection, RemoteError
from app.modules.catalog.schemas import (
    ConnectionTestIn,
    ConnectionTestResult,
    ImportSourceIn,
    ImportSourceRead,
    RemoteFileRead,
)
from app.modules.catalog.service import Invalid, now
from app.modules.partners import public as partners


def get_source(db: Session, source_id: int) -> ImportSource:
    source = db.get(ImportSource, source_id)
    if source is None:
        raise NotFound("Relève introuvable")
    return source


def read(db: Session, sources: list[ImportSource]) -> list[ImportSourceRead]:
    names = partners.partner_names(db, {s.partner_id for s in sources})
    profiles = {
        p.id: p.name
        for p in db.scalars(
            select(ImportProfile).where(
                ImportProfile.id.in_({s.profile_id for s in sources if s.profile_id})
            )
        )
    }
    result = []
    for s in sources:
        item = ImportSourceRead.model_validate(s)
        item.partner_name = names.get(s.partner_id, ("", None))[1]
        item.profile_name = profiles.get(s.profile_id)
        item.has_secret = bool(s.secret)
        result.append(item)
    return result


def list_sources(db: Session, partner_id: int | None) -> list[ImportSourceRead]:
    query = select(ImportSource).order_by(ImportSource.id)
    if partner_id:
        query = query.where(ImportSource.partner_id == partner_id)
    return read(db, list(db.scalars(query)))


def test_connection(db: Session, data: ConnectionTestIn) -> ConnectionTestResult:
    """Se connecte avec les paramètres saisis (sans rien enregistrer) et liste les fichiers.

    SFTP : renvoie l'empreinte du serveur, que l'utilisateur doit confirmer."""
    stored = get_source(db, data.source_id) if data.source_id else None
    if data.secret:
        secret = data.secret
    elif stored is not None and stored.secret:
        secret = secrets.decrypt(stored.secret)
    else:
        raise Invalid("Saisissez le mot de passe (ou la clé SSH)")
    cfg = config_of(stored or ImportSource(), secret)
    for field in (
        "protocol",
        "host",
        "port",
        "username",
        "auth_method",
        "tls_verify",
        "remote_dir",
    ):
        setattr(cfg, field, getattr(data, field))
    # L'empreinte n'est pas encore connue (ou pas encore confirmée) : on la lit et on la renvoie.
    cfg.host_key = None
    try:
        with Connection(cfg, accept_unknown_key=True) as remote:
            files = remote.list(data.remote_dir, data.pattern)
            host_key = remote.host_key
    except RemoteError as exc:
        raise Invalid(str(exc), code="connexion_impossible") from exc
    seen = _seen(db, stored.id) if stored else set()
    files.sort(key=lambda f: (f.mtime is not None, f.mtime, f.name), reverse=True)
    return ConnectionTestResult(
        host_key=host_key,
        host_key_changed=bool(
            stored and stored.host_key and host_key and stored.host_key != host_key
        ),
        files=[
            RemoteFileRead(
                name=f.name,
                size=f.size,
                mtime=f.mtime,
                already_seen=(f.name, f.size, f.mtime) in seen,
            )
            for f in files[:50]
        ],
    )


def save_source(
    db: Session, data: ImportSourceIn, source_id: int | None = None
) -> ImportSourceRead:
    partners.get_supplier(db, data.partner_id)
    profile = repo.get_profile(db, data.profile_id)
    if profile is None or profile.partner_id != data.partner_id:
        raise Invalid("Ce format d'import n'appartient pas à ce fournisseur")
    if data.protocol == "sftp" and not data.host_key:
        raise Invalid("Testez la connexion et confirmez l'empreinte du serveur avant d'enregistrer")
    source = get_source(db, source_id) if source_id else ImportSource()
    if not data.secret and not source.secret:
        raise Invalid("Saisissez le mot de passe (ou la clé SSH)")
    values = data.model_dump(exclude={"secret"})
    previous_interval = source.interval_hours
    for field, value in values.items():
        setattr(source, field, value)
    if data.secret:
        source.secret = secrets.encrypt(data.secret)  # 503 si SECRETS_KEY absente
    if source_id is None:
        source.next_check_at = now()  # première relève au prochain passage du worker
        db.add(source)
    elif previous_interval != data.interval_hours and source.last_check_at:
        from datetime import timedelta

        source.next_check_at = source.last_check_at + timedelta(hours=data.interval_hours)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict(
            f"Ce fournisseur a déjà une relève « {data.name} »", code="releve_existante"
        ) from exc
    return read(db, [source])[0]


def delete_source(db: Session, source_id: int) -> None:
    db.delete(get_source(db, source_id))
    db.commit()


def run_now(db: Session, ctx: RequestContext, source_id: int) -> ImportSourceRead:
    source = get_source(db, source_id)
    enqueue("catalog.poll_source", source.id, ctx.user_id, ctx.company_id, True)
    db.expire_all()
    return read(db, [get_source(db, source_id)])[0]


def secrets_configured() -> bool:
    key = get_settings().secrets_key
    return bool(key and key.get_secret_value())


def forget_seen_files(db: Session, source_id: int) -> None:
    """Oublier les fichiers déjà traités : le prochain passage reprend le plus récent."""
    get_source(db, source_id)
    db.query(ImportSourceFile).filter(ImportSourceFile.source_id == source_id).delete()
    db.commit()
