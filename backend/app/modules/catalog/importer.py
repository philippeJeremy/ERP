"""Moteur d'import des tarifs fournisseurs.

Trois temps, pour que rien ne soit écrit sans que l'utilisateur ait vu le résultat :
1. dépôt : le fichier est enregistré en base (`import_runs.content`) ;
2. analyse (tâche de fond) : chaque ligne est lue, contrôlée et comparée à la base ;
   le résultat (nouveau, prix modifié, inchangé, réactivé, arrêté, erreur) va dans
   `import_lines`. C'est l'aperçu ;
3. application (tâche de fond, après validation) : tout est écrit en UNE transaction
   (tout ou rien), puis le fichier est effacé.

Les manières d'amener le fichier (dépôt manuel aujourd'hui, FTP/SFTP demain) ne
changent que l'étape 1.
"""

import logging
from decimal import Decimal

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.context import RequestContext
from app.core.db import SessionLocal, set_db_context
from app.core.errors import Conflict, NotFound
from app.core.jobs import enqueue
from app.modules.catalog import repository as repo
from app.modules.catalog.files import FIELDS, FileError, read_table, suggest_mapping
from app.modules.catalog.models import (
    KINDS,
    LABEL_CLASSES,
    NOISE_CLASSES,
    SEASONS,
    VEHICLE_TYPES,
    Article,
    ArticleSupplier,
    ImportLine,
    ImportProfile,
    ImportRun,
)
from app.modules.catalog.schemas import FilePreview
from app.modules.catalog.service import Invalid, apply_tire, brand_for, default_designation, now
from app.modules.catalog.tires import gtin_is_valid, parse_designation, to_decimal
from app.modules.partners import public as partners

log = logging.getLogger(__name__)

# Garde-fou : au-delà, l'application demande une confirmation explicite (fichier tronqué ?).
MASS_DISCONTINUE_RATIO = 0.30
MASS_DISCONTINUE_MIN = 10

TIRE_FIELDS = (
    "vehicle_type", "season", "width", "aspect_ratio", "rim", "construction", "load_index",
    "speed_index", "reinforced", "runflat", "studded", "three_pmsf", "mud_snow",
    "fuel_class", "wet_class", "noise_db", "noise_class", "eprel_id",
)  # fmt: skip

# Valeurs écrites librement par les fournisseurs → nos codes.
_KIND_WORDS = {"pneu": "pneu", "pneumatique": "pneu", "tyre": "pneu", "tire": "pneu",
               "piece": "piece", "pièce": "piece", "part": "piece",
               "accessoire": "accessoire", "accessory": "accessoire"}  # fmt: skip
_SEASON_WORDS = {"ete": "ete", "été": "ete", "summer": "ete", "s": "ete",
                 "hiver": "hiver", "winter": "hiver", "w": "hiver",
                 "4 saisons": "4_saisons", "4saisons": "4_saisons", "all season": "4_saisons",
                 "allseason": "4_saisons", "4s": "4_saisons", "a": "4_saisons"}  # fmt: skip
_VEHICLE_WORDS = {"tourisme": "tourisme", "vl": "tourisme", "auto": "tourisme", "car": "tourisme",
                  "pcr": "tourisme", "4x4": "4x4", "suv": "4x4", "utilitaire": "utilitaire",
                  "camionnette": "utilitaire", "van": "utilitaire", "lt": "utilitaire",
                  "moto": "moto", "motorcycle": "moto", "scooter": "moto",
                  "poids lourd": "poids_lourd", "pl": "poids_lourd", "tbr": "poids_lourd",
                  "truck": "poids_lourd", "agricole": "agricole", "agri": "agricole",
                  "genie civil": "genie_civil", "gc": "genie_civil",
                  "otr": "genie_civil"}  # fmt: skip


def _word(value: str, table: dict[str, str]) -> str | None:
    return table.get(" ".join(value.lower().replace("_", " ").split())) if value else None


# --- 1. Aperçu d'un fichier (avant de créer le profil) ----------------------------------


def preview_file(
    content: bytes,
    filename: str,
    *,
    delimiter: str | None,
    encoding: str | None,
    sheet_name: str | None,
    header_row: int,
) -> FilePreview:
    try:
        table = read_table(
            content,
            filename,
            delimiter=delimiter,
            encoding=encoding,
            sheet_name=sheet_name,
            header_row=header_row,
            limit=10,
        )
    except FileError as exc:
        raise Invalid(str(exc), code="fichier_illisible") from exc
    return FilePreview(
        **{
            k: table.detected.get(k)
            for k in ("file_format", "delimiter", "encoding", "sheets", "sheet_name")
        },
        headers=table.headers,
        rows=table.rows,
        suggested_mapping=suggest_mapping(table.headers),
        fields=FIELDS,
    )


# --- 2. Dépôt -----------------------------------------------------------------------


def create_run(
    db: Session,
    ctx: RequestContext,
    *,
    profile_id: int,
    filename: str,
    content: bytes,
    source: str = "manuel",
) -> ImportRun:
    profile = repo.get_profile(db, profile_id)
    if profile is None:
        raise NotFound("Profil d'import introuvable")
    partners.get_supplier(db, profile.partner_id)
    if len(content) > get_settings().import_max_mb * 1024 * 1024:
        raise Invalid(f"Fichier trop volumineux (maximum {get_settings().import_max_mb} Mo)")
    if not content:
        raise Invalid("Le fichier est vide")
    run = ImportRun(
        profile_id=profile.id,
        partner_id=profile.partner_id,
        source=source,
        filename=filename[:255],
        file_size=len(content),
        content=content,
        full_catalog=profile.full_catalog,
        status="analyse",
    )
    db.add(run)
    db.commit()
    enqueue("catalog.analyze_import", run.id, ctx.user_id, ctx.company_id)
    db.refresh(run)
    return run


# --- 3. Analyse (tâche de fond) -------------------------------------------------------


def _row_values(row: list[str], columns: dict[str, int], profile: ImportProfile) -> dict:
    """Une ligne du fichier → valeurs normalisées. Lève ValueError avec un message clair."""
    raw = {fld: row[i].strip() for fld, i in columns.items()}
    v: dict = {}
    ean = raw.get("ean", "").replace(" ", "")
    if ean:
        if not ean.isdigit():
            raise ValueError(f"EAN « {raw['ean']} » : chiffres uniquement")
        # Excel supprime les 0 initiaux d'un EAN-13 (il le prend pour un nombre).
        if 10 <= len(ean) < 13 and not gtin_is_valid(ean) and gtin_is_valid(ean.zfill(13)):
            ean = ean.zfill(13)
        if not gtin_is_valid(ean):
            raise ValueError(f"EAN « {ean} » invalide (clé de contrôle)")
        v["ean"] = ean
    for fld in ("supplier_ref", "manufacturer_ref", "brand", "designation", "category", "eprel_id"):
        if raw.get(fld):
            v[fld] = raw[fld][
                : 250 if fld == "designation" else 100 if fld in ("brand", "category") else 50
            ]
    if not v.get("ean") and not v.get("supplier_ref"):
        raise ValueError("Ni code EAN ni référence fournisseur")
    price = to_decimal(raw.get("purchase_price"))
    if price is None:
        raise ValueError(f"Prix « {raw.get('purchase_price', '')} » illisible")
    if price < 0:
        raise ValueError("Prix négatif")
    v["purchase_price"] = str(price.quantize(Decimal("0.0001")))

    kind = _word(raw.get("kind", ""), _KIND_WORDS) or profile.default_kind
    v["kind"] = kind
    if kind != "pneu":
        return v

    # Caractéristiques pneu : d'abord la désignation, puis les colonnes (prioritaires).
    tire: dict = {}
    if profile.parse_designation and v.get("designation"):
        tire.update(parse_designation(v["designation"]))
    for fld in ("width", "rim"):
        if raw.get(fld) and (d := to_decimal(raw[fld])) is not None:
            tire[fld] = d
    if raw.get("aspect_ratio") and (d := to_decimal(raw["aspect_ratio"])) is not None:
        tire["aspect_ratio"] = int(d)
    for fld in ("load_index", "speed_index"):
        if raw.get(fld):
            tire[fld] = raw[fld].upper()[:10]
    if raw.get("season"):
        tire["season"] = _word(raw["season"], _SEASON_WORDS) or tire.get("season")
    if raw.get("vehicle_type"):
        tire["vehicle_type"] = _word(raw["vehicle_type"], _VEHICLE_WORDS) or tire.get(
            "vehicle_type"
        )
    for fld, allowed in (
        ("fuel_class", LABEL_CLASSES),
        ("wet_class", LABEL_CLASSES),
        ("noise_class", NOISE_CLASSES),
    ):
        letter = raw.get(fld, "").upper()[:1]
        if letter in allowed:
            tire[fld] = letter
    if raw.get("noise_db") and (d := to_decimal(raw["noise_db"])) is not None and 50 <= d <= 90:
        tire["noise_db"] = int(d)
    tire.setdefault("vehicle_type", profile.default_vehicle_type or "tourisme")
    if tire["vehicle_type"] not in VEHICLE_TYPES:
        tire["vehicle_type"] = "autre"
    if tire.get("season") not in (None, *SEASONS):
        tire.pop("season")
    if tire.get("speed_index") and not tire["speed_index"][:1].isalpha():
        tire.pop("speed_index")
    # Décimales en texte : le JSON n'a pas de type « décimal exact ».
    v["tire"] = {k: (str(val) if isinstance(val, Decimal) else val) for k, val in tire.items()}
    return v


def _analyze(db: Session, run: ImportRun) -> None:
    profile = repo.get_profile(db, run.profile_id) if run.profile_id else None
    if profile is None:
        raise FileError("Le profil d'import a été supprimé")
    try:
        table = read_table(
            run.content or b"",
            run.filename,
            delimiter=profile.delimiter,
            encoding=profile.encoding,
            sheet_name=profile.sheet_name,
            header_row=profile.header_row,
        )
    except FileError:
        raise
    positions = {h: i for i, h in enumerate(table.headers)}
    missing = [h for h in profile.mapping.values() if h not in positions]
    if missing:
        raise FileError(
            "Colonnes introuvables dans ce fichier : "
            + ", ".join(f"« {h} »" for h in missing)
            + ". Le format du fournisseur a peut-être changé : modifiez le profil."
        )
    columns = {fld: positions[header] for fld, header in profile.mapping.items()}

    # Ce qu'on connaît déjà : les liens de ce fournisseur, les articles par EAN.
    links = repo.links_of_partner(db, run.partner_id)
    by_ref = {link.supplier_ref: link for link in links if link.supplier_ref}
    by_article = {link.article_id: link for link in links}
    parsed: list[tuple[int, dict | None, str | None]] = []
    eans: set[str] = set()
    for offset, row in enumerate(table.rows):
        if not any(cell.strip() for cell in row):
            continue  # ligne vide
        line_no = table.first_line + offset
        try:
            values = _row_values(row, columns, profile)
            if "ean" in values:
                eans.add(values["ean"])
            parsed.append((line_no, values, None))
        except ValueError as exc:
            parsed.append((line_no, None, str(exc)))
    articles = repo.articles_by_ean(db, sorted(eans))

    lines: list[dict] = []
    counts = dict.fromkeys(("nouveau", "maj", "inchange", "reactive", "arret", "erreur"), 0)
    seen_links: set[int] = set()
    seen_keys: dict[str, int] = {}
    for line_no, values, error in parsed:
        line = {"run_id": run.id, "line_no": line_no, "data": values or {}, "article_id": None,
                "link_id": None, "old_price": None, "new_price": None, "error": error}  # fmt: skip
        if values is not None:
            key = values.get("ean") or f"ref:{values['supplier_ref']}"
            if key in seen_keys:
                error = f"Doublon de la ligne {seen_keys[key]}"
            else:
                seen_keys[key] = line_no
                article = articles.get(values.get("ean", ""))
                link = by_ref.get(values.get("supplier_ref", "")) or (
                    by_article.get(article.id) if article else None
                )
                if link is not None and link.id in seen_links:
                    error = "Même article que une ligne précédente (EAN ou référence)"
                elif link is not None:
                    seen_links.add(link.id)
                    line.update(article_id=link.article_id, link_id=link.id)
                    line["old_price"] = link.purchase_price
                    line["new_price"] = Decimal(values["purchase_price"])
                    if link.is_discontinued:
                        line["status"] = "reactive"
                    elif link.purchase_price != line["new_price"]:
                        line["status"] = "maj"
                    else:
                        line["status"] = "inchange"
                else:
                    if (
                        article is None
                        and not values.get("designation")
                        and not values.get("tire", {}).get("width")
                    ):
                        error = "Article inconnu et sans désignation : impossible de le créer"
                    else:
                        line["article_id"] = article.id if article else None
                        line["new_price"] = Decimal(values["purchase_price"])
                        line["status"] = "nouveau"
        if error:
            line["status"] = "erreur"
            line["error"] = error
        counts[line["status"]] += 1
        lines.append(line)

    # Fichier complet : les articles du fournisseur absents du fichier sont arrêtés.
    if run.full_catalog:
        for link in links:
            if link.id not in seen_links and not link.is_discontinued:
                lines.append({"run_id": run.id, "line_no": None, "status": "arret",
                              "article_id": link.article_id, "link_id": link.id,
                              "data": {"supplier_ref": link.supplier_ref,
                                       "designation": link.article.designation,
                                       "ean": link.article.ean},
                              "old_price": link.purchase_price, "new_price": None,
                              "error": None})  # fmt: skip
                counts["arret"] += 1

    for i in range(0, len(lines), 2000):
        db.execute(insert(ImportLine), lines[i : i + 2000])
    run.total_lines = len(parsed)
    run.new_count = counts["nouveau"]
    run.updated_count = counts["maj"]
    run.unchanged_count = counts["inchange"]
    run.reactivated_count = counts["reactive"]
    run.discontinued_count = counts["arret"]
    run.error_count = counts["erreur"]
    run.active_before = sum(1 for link in links if not link.is_discontinued)
    run.status = "pret"
    run.analyzed_at = now()


def analyze_job(run_id: int, user_id: int, company_id: int) -> None:
    with SessionLocal() as db:
        set_db_context(db, user_id=user_id, company_id=company_id)
        run = repo.get_run(db, run_id, for_update=True)
        if run is None or run.status != "analyse":
            return
        try:
            _analyze(db, run)
            db.commit()
        except Exception as exc:
            db.rollback()
            run = repo.get_run(db, run_id, for_update=True)
            run.status = "erreur"
            run.message = (
                str(exc) if isinstance(exc, FileError) else "Erreur inattendue pendant l'analyse"
            )
            if not isinstance(exc, FileError):
                log.exception("analyse de l'import %s", run_id)
            db.commit()


# --- 4. Application (tâche de fond) -----------------------------------------------------


def needs_confirmation(run: ImportRun) -> bool:
    return (
        run.discontinued_count >= MASS_DISCONTINUE_MIN
        and run.discontinued_count > MASS_DISCONTINUE_RATIO * max(run.active_before, 1)
    )


def get_run(db: Session, run_id: int) -> ImportRun:
    run = repo.get_run(db, run_id)
    if run is None:
        raise NotFound("Import introuvable")
    return run


def request_apply(db: Session, ctx: RequestContext, run_id: int, confirm: bool) -> ImportRun:
    run = repo.get_run(db, run_id, for_update=True)
    if run is None:
        raise NotFound("Import introuvable")
    if run.status != "pret":
        raise Conflict("Cet import n'est pas prêt à être appliqué", code="import_pas_pret")
    if needs_confirmation(run) and not confirm:
        raise Conflict(
            f"Cet import arrêterait {run.discontinued_count} articles sur {run.active_before} "
            "chez ce fournisseur. Vérifiez que le fichier est complet, puis confirmez.",
            code="confirmation_requise",
        )
    run.status = "application"
    run.applied_by = ctx.user_id
    db.commit()
    enqueue("catalog.apply_import", run.id, ctx.user_id, ctx.company_id)
    db.refresh(run)
    return run


def _apply(db: Session, run: ImportRun) -> None:
    lines, _ = repo.run_lines(db, run.id, None)
    links = {link.id: link for link in repo.links_of_partner(db, run.partner_id)}
    brands: dict = {}
    created: dict[str, Article] = {}
    stamp = now()
    for line in lines:
        data = line.data
        if line.status == "erreur" or line.status == "inchange":
            continue
        if line.status == "arret":
            link = links.get(line.link_id)
            if link is not None and not link.is_discontinued:
                link.is_discontinued = True
                link.discontinued_at = stamp
                link.last_import_id = run.id
            continue
        price = Decimal(data["purchase_price"])
        if line.status in ("maj", "reactive"):
            link = links.get(line.link_id)
            if link is None:
                continue  # supprimé entre l'analyse et l'application
            if link.purchase_price != price:
                link.purchase_price = price
                link.price_updated_at = stamp
            link.is_discontinued = False
            link.discontinued_at = None
            link.supplier_ref = link.supplier_ref or data.get("supplier_ref")
            link.last_import_id = run.id
            continue
        # « nouveau » : l'article existe (article_id) ou il faut le créer.
        article = repo.get_article(db, line.article_id) if line.article_id else None
        if article is None and data.get("ean"):
            # Créé entre-temps (par un autre import, une autre société) ?
            article = created.get(data["ean"]) or repo.get_article_by_ean(db, data["ean"])
        if article is None:
            brand = brand_for(db, data.get("brand"), brands)
            tire = data.get("tire")
            article = Article(
                kind=data["kind"] if data["kind"] in KINDS else "piece",
                ean=data.get("ean"),
                brand=brand,
                manufacturer_ref=data.get("manufacturer_ref"),
                designation=data.get("designation") or default_designation(brand, tire or {}),
                category=data.get("category"),
            )
            if article.kind == "pneu":
                spec = {k: v for k, v in (tire or {}).items() if k in TIRE_FIELDS}
                for k in ("width", "rim"):
                    if spec.get(k) is not None:
                        spec[k] = Decimal(spec[k])
                apply_tire(article, spec)
                if data.get("eprel_id"):
                    article.tire.eprel_id = data["eprel_id"]
            db.add(article)
            db.flush()
            if article.ean:
                created[article.ean] = article
        if repo.find_link(db, run.partner_id, article.id) is not None:
            continue
        db.add(
            ArticleSupplier(
                article_id=article.id,
                partner_id=run.partner_id,
                supplier_ref=data.get("supplier_ref"),
                purchase_price=price,
                price_updated_at=stamp,
                last_import_id=run.id,
            )
        )
        db.flush()
    run.status = "termine"
    run.applied_at = stamp
    run.content = None  # le fichier n'est plus utile


def apply_job(run_id: int, user_id: int, company_id: int) -> None:
    with SessionLocal() as db:
        set_db_context(db, user_id=user_id, company_id=company_id)
        run = repo.get_run(db, run_id, for_update=True)
        if run is None or run.status != "application":
            return
        try:
            _apply(db, run)
            db.commit()  # tout ou rien
        except Exception:
            db.rollback()
            log.exception("application de l'import %s", run_id)
            run = repo.get_run(db, run_id, for_update=True)
            run.status = "erreur"
            run.message = "Erreur pendant l'application : rien n'a été modifié. Relancez l'analyse."
            db.commit()


def cancel_run(db: Session, run_id: int) -> ImportRun:
    run = repo.get_run(db, run_id, for_update=True)
    if run is None:
        raise NotFound("Import introuvable")
    if run.status not in ("pret", "erreur"):
        raise Conflict(
            "Seul un import en attente de validation peut être annulé", code="import_pas_annulable"
        )
    run.status = "annule"
    run.content = None
    db.query(ImportLine).filter(ImportLine.run_id == run.id).delete()
    db.commit()
    return run
