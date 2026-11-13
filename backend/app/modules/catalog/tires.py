"""Lecture des dimensions de pneus et contrôle des codes-barres.

Les fournisseurs écrivent souvent tout dans la désignation :
« MICHELIN 205/55 R16 91V XL PRIMACY 4 » → largeur 205, série 55, radial, jante 16,
indice de charge 91, vitesse V, renforcé. Ce module extrait ces informations, pour
que la recherche « 2055516 » retrouve le pneu même si le fichier n'avait pas de colonnes.
"""

import re
from decimal import Decimal, InvalidOperation

from app.shared.validators import gtin_is_valid  # noqa: F401  (réexporté)

SPEED_INDEXES = "JKLMNPQRSTUHVWYZ"
HEAVY_RIMS = {Decimal("17.5"), Decimal("19.5"), Decimal("22.5"), Decimal("24.5")}

# 205/55 R16 · 205/55ZR16 · 315/80 R 22.5 · 195/70 R15C · 120/70 ZR 17 · 4.00-8
_SIZE = re.compile(
    r"(?<![\d.,])(?P<width>\d{2,3}(?:[.,]\d{1,2})?)\s*/\s*(?P<aspect>\d{2,3})\s*"
    r"(?P<cons>ZR|R|-|D|B)\s*F?\s*(?P<rim>\d{2}(?:[.,]\d)?)(?P<c>C)?(?![\d.])",
    re.IGNORECASE,
)
# Sans série : 12.5 R 20 · 7.50 R16 · 4.00-8 · 11 R22.5
_SIZE_NO_ASPECT = re.compile(
    r"(?<![\d.,/])(?P<width>\d{1,2}(?:[.,]\d{1,2})?)\s*(?P<cons>R|-|D)\s*"
    r"(?P<rim>\d{1,2}(?:[.,]\d)?)(?P<c>C)?(?![\d.])",
    re.IGNORECASE,
)
# Juste après la dimension : « 91V », « 91 V », « 154/150M », « (94Y) »
_INDEXES = re.compile(
    rf"^\s*\(?(?P<load>\d{{2,3}}(?:/\d{{2,3}})?)\s*\(?(?P<speed>[{SPEED_INDEXES}])\)?(?![A-Z])",
    re.IGNORECASE,
)

_FLAGS = {
    "reinforced": re.compile(r"\b(XL|EXTRA\s*LOAD|REINF(ORCED)?|RENFORC[EÉ])\b", re.I),
    "runflat": re.compile(r"\b(RUN\s*-?\s*FLAT|RFT|ROF|SSR|ZP|EMT|HRS|DSST|MOE|RFLAT)\b", re.I),
    "three_pmsf": re.compile(r"(\b3\s*PM?SF\b|❄)", re.I),
    "mud_snow": re.compile(r"\b(M\s*\+\s*S|M\s*&\s*S|M/S)", re.I),
    "studded": re.compile(r"\b(CLOUT[EÉ]S?|STUDDED|STUD)\b", re.I),
}
_SEASONS = [
    (
        "4_saisons",
        re.compile(
            r"(4\s*SAISONS|QUATRE\s*SAISONS|ALL\s*-?\s*SEASONS?|4\s*SEASONS?|ALLWEATHER|ALL\s*WEATHER)",
            re.I,
        ),
    ),
    ("hiver", re.compile(r"\b(HIVER|WINTER|SNOW|NEIGE|ALPIN|NORDIC)", re.I)),
    ("ete", re.compile(r"\b([EÉ]T[EÉ]\b|SUMMER)", re.I)),
]


def to_decimal(value: str | None) -> Decimal | None:
    """« 1 234,56 € » → Decimal('1234.56'). Vide ou illisible → None."""
    if value is None:
        return None
    text = str(value).strip().replace(" ", "").replace(" ", "").replace("€", "")
    if not text:
        return None
    if "," in text and "." in text:
        # 1.234,56 (français) ou 1,234.56 (anglais) : le dernier séparateur est la décimale.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def size_code(
    width: Decimal | str | None, aspect: int | None, rim: Decimal | str | None
) -> str | None:
    """Dimension « compacte » pour la recherche : 205/55 R16 → 2055516 ; 315/80 R22.5 → 31580225."""
    if width is None or rim is None:
        return None
    width, rim = Decimal(str(width)), Decimal(str(rim))
    parts = [f"{width.normalize():f}", str(aspect or ""), f"{rim.normalize():f}"]
    return re.sub(r"\D", "", "".join(parts)) or None


def size_label(spec: dict) -> str | None:
    """Affichage : 205/55 R16 91V."""
    width, rim = spec.get("width"), spec.get("rim")
    if width is None or rim is None:
        return None
    w = f"{Decimal(str(width)).normalize():f}"
    r = f"{Decimal(str(rim)).normalize():f}"
    cons = spec.get("construction") or "R"
    sep = " " if cons != "-" else ""
    label = f"{w}/{spec['aspect_ratio']}" if spec.get("aspect_ratio") else w
    label += f"{sep}{cons}{r}"
    indexes = f"{spec.get('load_index') or ''}{spec.get('speed_index') or ''}"
    return f"{label} {indexes}".strip()


def search_digits(query: str) -> str | None:
    """« 205/55 R16 », « 205 55 16 », « 2055516 » → « 2055516 » si ça ressemble à une dimension."""
    if not re.fullmatch(r"[\d\s/.,RrZz-]+", query.strip()):
        return None
    digits = re.sub(r"\D", "", query)
    return digits if len(digits) >= 5 else None


def parse_designation(text: str) -> dict:
    """Extrait d'une désignation ce qu'on peut sur le pneu (seulement ce qui est trouvé)."""
    result: dict = {}
    if not text:
        return result
    match = _SIZE.search(text) or _SIZE_NO_ASPECT.search(text)
    if match:
        width = to_decimal(match["width"])
        rim = to_decimal(match["rim"])
        aspect = (
            int(match["aspect"])
            if "aspect" in match.groupdict() and match.groupdict().get("aspect")
            else None
        )
        cons = match["cons"].upper()
        result.update(width=width, aspect_ratio=aspect, rim=rim, construction=cons)
        indexes = _INDEXES.match(text[match.end() :])
        if indexes:
            result["load_index"] = indexes["load"]
            result["speed_index"] = indexes["speed"].upper()
        if match["c"] or re.search(r"\bLT\b", text):
            result["vehicle_type"] = "utilitaire"
        if rim in HEAVY_RIMS:
            result["vehicle_type"] = "poids_lourd"
    for flag, pattern in _FLAGS.items():
        if pattern.search(text):
            result[flag] = True
    for season, pattern in _SEASONS:
        if pattern.search(text):
            result["season"] = season
            break
    return result
