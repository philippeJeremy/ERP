"""Routes HTTP du module catalog."""

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.context import RequestContext
from app.core.db import get_db
from app.modules.auth.public import require
from app.modules.catalog import importer, service, sources
from app.modules.catalog import repository as repo
from app.modules.catalog.schemas import (
    ApplyImport,
    ArticleCreate,
    ArticlePage,
    ArticleRead,
    ArticleSupplierIn,
    ArticleSupplierPage,
    ArticleSupplierRead,
    ArticleSupplierUpdate,
    ArticleUpdate,
    BrandRead,
    ConnectionTestIn,
    ConnectionTestResult,
    FilePreview,
    ImportLinePage,
    ImportProfileIn,
    ImportProfileRead,
    ImportRunPage,
    ImportRunRead,
    ImportSourceIn,
    ImportSourceRead,
)
from app.modules.partners import public as partners

router = APIRouter(prefix="/catalog", tags=["Catalogue"])

READ = Depends(require("catalog:read"))
MANAGE = Depends(require("catalog:manage"))


# --- Articles ------------------------------------------------------------------------


@router.get("/articles", response_model=ArticlePage, dependencies=[READ])
def list_articles(
    kind: Literal["pneu", "piece", "accessoire"] | None = None,
    q: str | None = Query(
        None,
        max_length=100,
        description="Désignation, code, EAN, référence, marque ou dimension (205/55R16)",
    ),
    season: Literal["ete", "hiver", "4_saisons"] | None = None,
    vehicle_type: str | None = Query(None, max_length=20),
    partner_id: int | None = None,
    active: bool | None = None,
    sort: Literal["code", "designation", "brand", "size", "best_price"] = "designation",
    order: Literal["asc", "desc"] = "asc",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return service.list_articles(
        db, kind=kind, q=q, season=season, vehicle_type=vehicle_type, partner_id=partner_id,
        active=active, sort=sort, order=order, limit=limit, offset=offset,
    )  # fmt: skip


@router.post("/articles", response_model=ArticleRead, status_code=201, dependencies=[MANAGE])
def create_article(data: ArticleCreate, db: Session = Depends(get_db)):
    return service.create_article(db, data)


@router.get("/articles/{article_id}", response_model=ArticleRead, dependencies=[READ])
def get_article(article_id: int, db: Session = Depends(get_db)):
    return service.get_article(db, article_id)


@router.patch("/articles/{article_id}", response_model=ArticleRead, dependencies=[MANAGE])
def update_article(article_id: int, data: ArticleUpdate, db: Session = Depends(get_db)):
    return service.update_article(db, article_id, data)


@router.delete("/articles/{article_id}", status_code=204, dependencies=[MANAGE])
def delete_article(article_id: int, db: Session = Depends(get_db)):
    service.delete_article(db, article_id)


@router.get("/brands", response_model=list[BrandRead], dependencies=[READ])
def brands(q: str | None = Query(None, max_length=100), db: Session = Depends(get_db)):
    return repo.search_brands(db, q)


# --- Fournisseurs des articles -------------------------------------------------------


@router.get(
    "/articles/{article_id}/suppliers",
    response_model=list[ArticleSupplierRead],
    dependencies=[READ],
)
def article_suppliers(article_id: int, db: Session = Depends(get_db)):
    """Les fournisseurs de l'article dans la société courante, et leurs prix."""
    return service.article_suppliers(db, article_id)


@router.post(
    "/articles/{article_id}/suppliers",
    response_model=ArticleSupplierRead,
    status_code=201,
    dependencies=[MANAGE],
)
def add_supplier(article_id: int, data: ArticleSupplierIn, db: Session = Depends(get_db)):
    return service.add_supplier(db, article_id, data)


@router.get("/article-suppliers", response_model=ArticleSupplierPage, dependencies=[READ])
def search_article_suppliers(
    partner_id: int | None = None,
    q: str | None = Query(None, max_length=100),
    discontinued: bool | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Les articles d'un fournisseur (onglet « Articles » de la fiche fournisseur)."""
    return service.search_links(
        db, partner_id=partner_id, q=(q or "").strip() or None, discontinued=discontinued,
        limit=limit, offset=offset,
    )  # fmt: skip


@router.patch(
    "/article-suppliers/{link_id}", response_model=ArticleSupplierRead, dependencies=[MANAGE]
)
def update_article_supplier(
    link_id: int, data: ArticleSupplierUpdate, db: Session = Depends(get_db)
):
    return service.update_supplier_link(db, link_id, data)


@router.delete("/article-suppliers/{link_id}", status_code=204, dependencies=[MANAGE])
def delete_article_supplier(link_id: int, db: Session = Depends(get_db)):
    service.delete_supplier_link(db, link_id)


# --- Imports tarifs ------------------------------------------------------------------

IMPORT = Depends(require("catalog:import"))


async def _read_upload(file: UploadFile) -> bytes:
    limit = get_settings().import_max_mb * 1024 * 1024
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise service.Invalid(
            f"Fichier trop volumineux (maximum {get_settings().import_max_mb} Mo)"
        )
    return content


@router.post("/imports/preview", response_model=FilePreview, dependencies=[IMPORT])
async def preview(
    file: UploadFile = File(...),
    delimiter: str | None = Form(None, max_length=1),
    encoding: Literal["utf-8-sig", "cp1252"] | None = Form(None),
    sheet_name: str | None = Form(None, max_length=100),
    header_row: int = Form(1, ge=1, le=50),
):
    """Les 10 premières lignes du fichier et une proposition de correspondance des
    colonnes. Rien n'est enregistré."""
    content = await _read_upload(file)
    # Lecture du fichier (synchrone, parfois longue) dans un thread : la boucle asyncio
    # de l'API reste libre pour les autres requêtes.
    return await run_in_threadpool(
        importer.preview_file, content, file.filename or "fichier", delimiter=delimiter or None,
        encoding=encoding, sheet_name=sheet_name or None, header_row=header_row,
    )  # fmt: skip


@router.get("/import-profiles", response_model=list[ImportProfileRead], dependencies=[IMPORT])
def list_profiles(partner_id: int | None = None, db: Session = Depends(get_db)):
    return service.list_profiles(db, partner_id)


@router.post(
    "/import-profiles", response_model=ImportProfileRead, status_code=201, dependencies=[IMPORT]
)
def create_profile(data: ImportProfileIn, db: Session = Depends(get_db)):
    return service.save_profile(db, data)


@router.put(
    "/import-profiles/{profile_id}", response_model=ImportProfileRead, dependencies=[IMPORT]
)
def update_profile(profile_id: int, data: ImportProfileIn, db: Session = Depends(get_db)):
    return service.save_profile(db, data, profile_id)


@router.delete("/import-profiles/{profile_id}", status_code=204, dependencies=[IMPORT])
def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    service.delete_profile(db, profile_id)


def _run_read(db: Session, run) -> ImportRunRead:
    read = ImportRunRead.model_validate(run)
    read.partner_name = partners.partner_names(db, {run.partner_id}).get(
        run.partner_id, ("", None)
    )[1]
    read.needs_confirmation = run.status == "pret" and importer.needs_confirmation(run)
    return read


@router.post("/imports", response_model=ImportRunRead, status_code=status.HTTP_201_CREATED)
async def upload(
    profile_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    ctx: RequestContext = IMPORT,
):
    """Dépose un fichier : l'analyse démarre en tâche de fond (statut « analyse »)."""
    content = await _read_upload(file)
    # Base de données et envoi au worker : code synchrone, exécuté dans un thread.
    run = await run_in_threadpool(
        importer.create_run,
        db, ctx, profile_id=profile_id, filename=file.filename or "fichier", content=content,
    )  # fmt: skip
    return await run_in_threadpool(_run_read, db, run)


@router.get("/imports", response_model=ImportRunPage, dependencies=[IMPORT])
def list_imports(
    partner_id: int | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    runs, total = repo.list_runs(db, partner_id, limit, offset)
    return ImportRunPage(items=[_run_read(db, r) for r in runs], total=total)


@router.get("/imports/{run_id}", response_model=ImportRunRead, dependencies=[IMPORT])
def get_import(run_id: int, db: Session = Depends(get_db)):
    return _run_read(db, importer.get_run(db, run_id))


@router.get("/imports/{run_id}/lines", response_model=ImportLinePage, dependencies=[IMPORT])
def import_lines(
    run_id: int,
    status: Literal["nouveau", "maj", "inchange", "reactive", "arret", "erreur"] | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    importer.get_run(db, run_id)
    lines, total = repo.run_lines(db, run_id, status, limit, offset)
    return ImportLinePage(items=lines, total=total)


@router.post("/imports/{run_id}/apply", response_model=ImportRunRead)
def apply_import(
    run_id: int, data: ApplyImport, db: Session = Depends(get_db), ctx: RequestContext = IMPORT
):
    return _run_read(db, importer.request_apply(db, ctx, run_id, data.confirm_discontinue))


@router.post("/imports/{run_id}/cancel", response_model=ImportRunRead, dependencies=[IMPORT])
def cancel_import(run_id: int, db: Session = Depends(get_db)):
    return _run_read(db, importer.cancel_run(db, run_id))


# --- Relèves automatiques ------------------------------------------------------------


@router.get("/import-sources", response_model=list[ImportSourceRead], dependencies=[IMPORT])
def list_sources(partner_id: int | None = None, db: Session = Depends(get_db)):
    return sources.list_sources(db, partner_id)


@router.get("/import-sources/settings", dependencies=[IMPORT])
def sources_settings():
    """Le serveur sait-il chiffrer les mots de passe ? (sinon : SECRETS_KEY à configurer)."""
    return {"secrets_configured": sources.secrets_configured()}


@router.post("/import-sources/test", response_model=ConnectionTestResult, dependencies=[IMPORT])
def test_source(data: ConnectionTestIn, db: Session = Depends(get_db)):
    """Connexion d'essai : liste les fichiers trouvés et, en SFTP, l'empreinte du serveur."""
    return sources.test_connection(db, data)


@router.post(
    "/import-sources", response_model=ImportSourceRead, status_code=201, dependencies=[IMPORT]
)
def create_source(data: ImportSourceIn, db: Session = Depends(get_db)):
    return sources.save_source(db, data)


@router.put("/import-sources/{source_id}", response_model=ImportSourceRead, dependencies=[IMPORT])
def update_source(source_id: int, data: ImportSourceIn, db: Session = Depends(get_db)):
    return sources.save_source(db, data, source_id)


@router.delete("/import-sources/{source_id}", status_code=204, dependencies=[IMPORT])
def delete_source(source_id: int, db: Session = Depends(get_db)):
    sources.delete_source(db, source_id)


@router.post("/import-sources/{source_id}/run", response_model=ImportSourceRead)
def run_source(source_id: int, db: Session = Depends(get_db), ctx: RequestContext = IMPORT):
    """« Relever maintenant » : la relève part tout de suite dans le worker."""
    return sources.run_now(db, ctx, source_id)


@router.post("/import-sources/{source_id}/forget", status_code=204, dependencies=[IMPORT])
def forget_files(source_id: int, db: Session = Depends(get_db)):
    """Oublier les fichiers déjà traités (pour réimporter le dernier fichier)."""
    sources.forget_seen_files(db, source_id)
