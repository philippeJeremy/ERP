"""Lecture des fichiers tarifs fournisseurs : CSV/TXT, Excel (.xlsx) et ancien Excel (.xls).

Tout est ramené au même format : une liste de titres de colonnes et des lignes de
textes. Le reste du moteur d'import ne sait pas d'où viennent les données.
"""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

MAX_LINES = 300_000
ENCODINGS = ("utf-8-sig", "cp1252")  # UTF-8 (avec ou sans BOM), sinon Windows (Excel français)


class FileError(Exception):
    """Fichier illisible : message destiné à l'utilisateur."""


@dataclass
class Table:
    headers: list[str]
    rows: list[list[str]]  # chaque ligne : une valeur texte par colonne
    first_line: int  # numéro (dans le fichier) de la 1re ligne de données
    detected: dict = field(default_factory=dict)  # format, séparateur, encodage, onglets


def file_format_of(filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext in ("csv", "txt", "tsv"):
        return "csv"
    if ext in ("xlsx", "xlsm", "xls"):
        return "excel"
    raise FileError("Format non pris en charge : envoyez un fichier .csv, .txt, .xlsx ou .xls")


def _cell(value: object) -> str:
    """Valeur Excel → texte. 3528701234560.0 (EAN lu comme nombre) → « 3528701234560 »."""
    if value is None:
        return ""
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, Decimal):
        return f"{value:f}"
    if isinstance(value, datetime | date):
        return value.strftime("%d/%m/%Y")
    return str(value).strip()


def _decode(content: bytes, encoding: str | None) -> tuple[str, str]:
    for enc in [encoding] if encoding else ENCODINGS:
        try:
            return content.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    raise FileError("Encodage du fichier non reconnu (ni UTF-8, ni Windows-1252)")


def _read_csv(
    content: bytes, delimiter: str | None, encoding: str | None
) -> tuple[list[list[str]], dict]:
    text, enc = _decode(content, encoding)
    if not delimiter:
        sample = text[:20_000]
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
        except csv.Error:
            # Pas de détection fiable : le plus fréquent sur la ligne de titres.
            first = sample.splitlines()[0] if sample else ""
            delimiter = max(";,\t|", key=first.count)
    rows = [[c.strip() for c in row] for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
    return rows, {"delimiter": delimiter, "encoding": enc}


def _read_xlsx(
    content: bytes, sheet: str | None, limit: int | None
) -> tuple[list[list[str]], dict]:
    from openpyxl import load_workbook

    try:
        # read_only : lit la feuille ligne par ligne, sans tout charger en mémoire.
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # fichier corrompu, protégé par mot de passe…
        raise FileError("Fichier Excel illisible (corrompu ou protégé ?)") from exc
    try:
        sheets = book.sheetnames
        if sheet and sheet not in sheets:
            raise FileError(f"L'onglet « {sheet} » n'existe pas (onglets : {', '.join(sheets)})")
        ws = book[sheet or sheets[0]]
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append([_cell(v) for v in row])
            if limit and len(rows) >= limit:
                break
        return rows, {"sheets": sheets, "sheet_name": ws.title}
    finally:
        book.close()


def _read_xls(content: bytes, sheet: str | None, limit: int | None) -> tuple[list[list[str]], dict]:
    import xlrd

    try:
        book = xlrd.open_workbook(file_contents=content)
    except Exception as exc:
        raise FileError("Fichier Excel (.xls) illisible") from exc
    sheets = book.sheet_names()
    if sheet and sheet not in sheets:
        raise FileError(f"L'onglet « {sheet} » n'existe pas (onglets : {', '.join(sheets)})")
    ws = book.sheet_by_name(sheet or sheets[0])
    count = ws.nrows if not limit else min(limit, ws.nrows)
    rows = [[_cell(v) for v in ws.row_values(i)] for i in range(count)]
    return rows, {"sheets": sheets, "sheet_name": ws.name}


def read_table(
    content: bytes,
    filename: str,
    *,
    delimiter: str | None = None,
    encoding: str | None = None,
    sheet_name: str | None = None,
    header_row: int = 1,
    limit: int | None = None,
) -> Table:
    """Lit le fichier. `limit` : nombre de lignes à lire (aperçu) ; None = tout."""
    fmt = file_format_of(filename)
    read_limit = header_row + limit if limit else None
    if fmt == "csv":
        rows, detected = _read_csv(content, delimiter, encoding)
    elif filename.lower().endswith(".xls"):
        rows, detected = _read_xls(content, sheet_name, read_limit)
    else:
        rows, detected = _read_xlsx(content, sheet_name, read_limit)
    detected["file_format"] = fmt
    if len(rows) < header_row:
        raise FileError(f"Le fichier contient moins de {header_row} ligne(s)")
    headers = rows[header_row - 1]
    data = rows[header_row:]
    if read_limit is None and len(data) > MAX_LINES:
        raise FileError(f"Fichier trop long : {len(data)} lignes (maximum {MAX_LINES})")
    if limit:
        data = data[:limit]
    # Colonnes sans titre : « Colonne 5 » (lettre Excel peu parlante dans un CSV).
    headers = [h or f"Colonne {i + 1}" for i, h in enumerate(headers)]
    width = len(headers)
    data = [(r + [""] * width)[:width] for r in data]
    return Table(headers=headers, rows=data, first_line=header_row + 1, detected=detected)


# --- Proposition automatique de correspondance des colonnes --------------------------

FIELDS: dict[str, str] = {
    "ean": "Code EAN (code-barres)",
    "supplier_ref": "Référence fournisseur",
    "manufacturer_ref": "Référence fabricant",
    "brand": "Marque",
    "designation": "Désignation",
    "purchase_price": "Prix d'achat HT",
    "kind": "Type d'article (pneu, pièce, accessoire)",
    "category": "Catégorie",
    "vehicle_type": "Type de véhicule",
    "season": "Saison",
    "width": "Largeur",
    "aspect_ratio": "Série (hauteur)",
    "rim": "Jante (diamètre)",
    "load_index": "Indice de charge",
    "speed_index": "Indice de vitesse",
    "fuel_class": "Étiquette UE : carburant",
    "wet_class": "Étiquette UE : adhérence",
    "noise_db": "Étiquette UE : bruit (dB)",
    "noise_class": "Étiquette UE : classe de bruit",
    "eprel_id": "N° EPREL",
}

_ALIASES: dict[str, list[str]] = {
    "ean": [
        "ean",
        "ean13",
        "gtin",
        "code ean",
        "code barre",
        "code barres",
        "codebarre",
        "barcode",
        "ean code",
    ],
    "supplier_ref": [
        "ref",
        "reference",
        "ref fournisseur",
        "reference fournisseur",
        "code article",
        "code produit",
        "article",
        "sku",
        "item",
        "code",
        "ref article",
        "item code",
    ],
    "manufacturer_ref": [
        "ref fabricant",
        "reference fabricant",
        "cai",
        "mpn",
        "ref constructeur",
        "manufacturer ref",
        "manufacturer code",
        "code fabricant",
    ],
    "brand": ["marque", "brand", "fabricant", "manufacturer", "make"],
    "designation": [
        "designation",
        "libelle",
        "description",
        "produit",
        "desc",
        "article description",
        "nom",
        "designation article",
        "libelle article",
    ],
    "purchase_price": [
        "prix",
        "prix net",
        "prix achat",
        "prix d achat",
        "net",
        "prix ht",
        "prix net ht",
        "tarif",
        "price",
        "net price",
        "prix unitaire",
        "pu",
        "pu net",
        "prix remise",
    ],
    "kind": ["type article", "famille", "type produit"],
    "category": ["categorie", "category", "sous famille", "gamme"],
    "vehicle_type": ["type vehicule", "vehicule", "categorie vehicule", "usage", "segment"],
    "season": ["saison", "season"],
    "width": ["largeur", "width", "section"],
    "aspect_ratio": ["serie", "hauteur", "aspect", "profil", "ratio", "aspect ratio"],
    "rim": ["jante", "diametre", "rim", "diametre jante", "inch", "pouces"],
    "load_index": ["indice charge", "indice de charge", "ic", "load index", "li", "charge"],
    "speed_index": ["indice vitesse", "indice de vitesse", "iv", "speed index", "si", "vitesse"],
    "fuel_class": [
        "carburant",
        "classe carburant",
        "rr",
        "rolling resistance",
        "consommation",
        "efficacite energetique",
        "fuel",
    ],
    "wet_class": ["adherence", "adherence sol mouille", "wet", "wet grip", "mouille", "wg"],
    "noise_db": ["bruit", "bruit db", "noise", "db", "bruit exterieur", "noise db"],
    "noise_class": ["classe bruit", "noise class", "classe de bruit"],
    "eprel_id": ["eprel", "code eprel", "eprel id", "id eprel"],
}


def normalize_header(header: str) -> str:
    """« Désignation_Article » → « designation article » (sans accents ni ponctuation)."""
    text = unicodedata.normalize("NFKD", header).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def suggest_mapping(headers: list[str]) -> dict[str, str]:
    """Propose « champ ERP → colonne » d'après les titres. Chaque colonne ne sert qu'une fois."""
    normalized = {h: normalize_header(h) for h in headers}
    mapping: dict[str, str] = {}
    used: set[str] = set()
    # 1) correspondances exactes ; 2) le titre commence par un synonyme assez long.
    for exact in (True, False):
        for fld, aliases in _ALIASES.items():
            if fld in mapping:
                continue
            for header, norm in normalized.items():
                if header in used:
                    continue
                if fld == "purchase_price" and re.search(r"conseill|public|pvc|ppc|brut", norm):
                    continue  # un prix public conseillé n'est pas un prix d'achat
                hit = (
                    norm in aliases
                    if exact
                    else any(len(a) >= 4 and norm.startswith(a + " ") for a in aliases)
                )
                if hit:
                    mapping[fld] = header
                    used.add(header)
                    break
    return mapping
