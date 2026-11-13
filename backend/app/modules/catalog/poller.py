"""Relève automatique des tarifs : aller chercher le fichier, puis le moteur d'import.

Le worker lance `poll_due_sources` toutes les 5 minutes : pour chaque relève dont
l'heure est venue (toutes sociétés confondues), on se connecte, on prend le fichier le
plus récent qu'on n'a pas encore traité, on l'analyse comme un import manuel, et on
l'applique tout seul si la relève le permet et que l'analyse est propre.
"""

import logging
from datetime import timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core import secrets
from app.core.config import get_settings
from app.core.db import SessionLocal, set_db_context
from app.core.errors import DomainError
from app.modules.catalog import importer
from app.modules.catalog import repository as repo
from app.modules.catalog.files import FileError
from app.modules.catalog.models import ImportRun, ImportSource, ImportSourceFile
from app.modules.catalog.remote import Connection, RemoteError, SourceConfig
from app.modules.catalog.service import now

log = logging.getLogger(__name__)

# Application automatique seulement si l'analyse est « propre ».
AUTO_APPLY_MAX_ERROR_RATIO = 0.05


def config_of(source: ImportSource, secret: str | None = None) -> SourceConfig:
    return SourceConfig(
        protocol=source.protocol,
        host=source.host,
        port=source.port,
        username=source.username,
        auth_method=source.auth_method,
        secret=secret
        if secret is not None
        else (secrets.decrypt(source.secret) if source.secret else ""),
        host_key=source.host_key,
        tls_verify=source.tls_verify,
        remote_dir=source.remote_dir,
    )


def _seen(db: Session, source_id: int) -> set[tuple]:
    rows = db.execute(
        select(ImportSourceFile.filename, ImportSourceFile.size, ImportSourceFile.mtime).where(
            ImportSourceFile.source_id == source_id
        )
    )
    return {tuple(r) for r in rows}


def clean_enough(run: ImportRun) -> bool:
    return (
        run.status == "pret"
        and not importer.needs_confirmation(run)
        and run.error_count <= AUTO_APPLY_MAX_ERROR_RATIO * max(run.total_lines, 1)
    )


def _poll(db: Session, source: ImportSource, user_id: int, company_id: int) -> None:
    if source.profile_id is None or repo.get_profile(db, source.profile_id) is None:
        raise RemoteError("Le format d'import de cette relève a été supprimé")
    max_bytes = get_settings().import_max_mb * 1024 * 1024
    with Connection(config_of(source)) as remote:
        files = remote.list(source.remote_dir, source.pattern)
        seen = _seen(db, source.id)
        new = [f for f in files if (f.name, f.size, f.mtime) not in seen]
        if not new:
            source.last_status = "aucun_fichier"
            source.last_message = (
                f"Aucun nouveau fichier ({len(files)} « {source.pattern} » déjà traité(s))"
                if files
                else f"Aucun fichier « {source.pattern} » dans {source.remote_dir}"
            )
            return
        # Le plus récent seulement : les plus anciens sont dépassés par lui.
        new.sort(key=lambda f: (f.mtime is not None, f.mtime, f.name))
        latest = new[-1]
        for old in new[:-1]:
            db.add(ImportSourceFile(source_id=source.id, filename=old.name, size=old.size,
                                    mtime=old.mtime, status="ignore"))  # fmt: skip
        content = remote.download(source.remote_dir, latest.name, max_bytes)

    profile = repo.get_profile(db, source.profile_id)
    run = ImportRun(
        profile_id=profile.id,
        partner_id=source.partner_id,
        source=source.protocol if source.protocol != "ftps" else "ftp",
        filename=latest.name[:255],
        file_size=len(content),
        content=content,
        full_catalog=profile.full_catalog,
        status="analyse",
    )
    db.add(run)
    db.flush()
    db.add(ImportSourceFile(source_id=source.id, filename=latest.name, size=latest.size,
                            mtime=latest.mtime, status="importe", run_id=run.id))  # fmt: skip
    source.last_run_id = run.id
    db.commit()

    # Analyse tout de suite (on est déjà dans le worker), dans sa propre transaction.
    importer.analyze_job(run.id, user_id, company_id)
    db.refresh(run)
    summary = (
        f"{latest.name} : {run.new_count} nouveaux, {run.updated_count} prix modifiés, "
        f"{run.discontinued_count} arrêtés, {run.error_count} erreurs"
    )
    if run.status == "erreur":
        raise RemoteError(f"{latest.name} : {run.message}")
    if source.auto_apply and clean_enough(run):
        run.status = "application"
        run.applied_by = user_id
        db.commit()
        importer.apply_job(run.id, user_id, company_id)
        db.refresh(run)
        summary += (
            " — appliqué automatiquement"
            if run.status == "termine"
            else " — échec de l'application"
        )
    else:
        summary += " — en attente de validation"
    source.last_status = "ok"
    source.last_message = summary


def poll_source(source_id: int, user_id: int, company_id: int, force: bool = False) -> None:
    """Une relève. `force` : « Relever maintenant », même si l'heure n'est pas venue."""
    with SessionLocal() as db:
        set_db_context(db, user_id=user_id, company_id=company_id)
        # SKIP LOCKED : si une autre exécution traite déjà cette relève, on passe.
        source = db.scalar(
            select(ImportSource)
            .where(ImportSource.id == source_id)
            .with_for_update(skip_locked=True)
        )
        if source is None:
            return
        if not force and (
            not source.is_active or (source.next_check_at and source.next_check_at > now())
        ):
            return
        source.last_check_at = now()
        source.next_check_at = now() + timedelta(hours=source.interval_hours)
        try:
            _poll(db, source, user_id, company_id)
        except (RemoteError, FileError, DomainError) as exc:
            db.rollback()
            source = db.get(ImportSource, source_id)
            source.last_check_at = now()
            source.next_check_at = now() + timedelta(hours=source.interval_hours)
            source.last_status = "erreur"
            source.last_message = str(exc)
        except Exception:
            log.exception("relève %s", source_id)
            db.rollback()
            source = db.get(ImportSource, source_id)
            source.last_check_at = now()
            source.next_check_at = now() + timedelta(hours=source.interval_hours)
            source.last_status = "erreur"
            source.last_message = (
                "Erreur inattendue pendant la relève (voir les journaux du worker)"
            )
        db.commit()


def poll_due_sources() -> int:
    """Toutes les relèves dues, toutes sociétés : appelée par le cron du worker."""
    with SessionLocal() as db:
        # Fonction SECURITY DEFINER (migration 0008) : voit au-delà de la RLS.
        due = db.execute(
            text("SELECT id, company_id, user_id FROM catalog.due_import_sources()")
        ).all()
    for source_id, company_id, user_id in due:
        poll_source(source_id, user_id, company_id)
    return len(due)
