"""Schéma PostgreSQL `catalog` : articles (pneus, pièces, accessoires) et imports tarifs.

- Le catalogue (marques, articles, caractéristiques pneu) est COMMUN au groupe : un
  pneu (un EAN) n'existe qu'une fois, quelle que soit la société qui l'achète.
- Ce qui dépend de la société est protégé par la Row-Level Security : les fournisseurs
  d'un article et leurs prix d'achat, les profils et l'historique des imports.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, deferred, mapped_column, relationship

from app.shared.models import Base, BusinessEntity, CompanyScopedMixin, IdMixin

KINDS = ("pneu", "piece", "accessoire")
VEHICLE_TYPES = (
    "tourisme",
    "4x4",
    "utilitaire",
    "moto",
    "poids_lourd",
    "agricole",
    "genie_civil",
    "autre",
)
SEASONS = ("ete", "hiver", "4_saisons")
LABEL_CLASSES = ("A", "B", "C", "D", "E")
NOISE_CLASSES = ("A", "B", "C")
RUN_STATUSES = ("analyse", "pret", "application", "termine", "erreur", "annule")
LINE_STATUSES = ("nouveau", "maj", "inchange", "reactive", "arret", "erreur")


def _in(column: str, values: tuple[str, ...], nullable: bool = False) -> str:
    rule = f"{column} IN ({', '.join(repr(v) for v in values)})"
    return f"{column} IS NULL OR {rule}" if nullable else rule


class Brand(Base, BusinessEntity):
    __tablename__ = "brands"
    __table_args__ = (
        # « Michelin » et « MICHELIN » sont la même marque.
        Index("uq_brands_lower_name", func.lower(text("name")), unique=True),
        {"schema": "catalog"},
    )

    name: Mapped[str] = mapped_column(String(100))


class Article(Base, BusinessEntity):
    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint("code"),
        Index("uq_articles_ean", "ean", unique=True, postgresql_where=text("ean IS NOT NULL")),
        Index("ix_articles_brand_ref", "brand_id", "manufacturer_ref"),
        CheckConstraint(_in("kind", KINDS), name="kind"),
        CheckConstraint("ean ~ '^[0-9]{8}$|^[0-9]{12,14}$'", name="ean_format"),
        {"schema": "catalog"},
    )

    # Code article interne (A0000001…), tiré d'une séquence PostgreSQL (créée dans la
    # migration) : contrairement aux factures, un trou dans la numérotation des
    # articles n'a aucune conséquence.
    code: Mapped[str] = mapped_column(
        String(20),
        server_default=text("'A' || lpad(nextval('catalog.article_code_seq')::text, 7, '0')"),
    )
    kind: Mapped[str] = mapped_column(String(20))
    ean: Mapped[str | None] = mapped_column(String(14))  # code-barres GTIN (EAN-13 le plus souvent)
    brand_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("catalog.brands.id"), index=True
    )
    manufacturer_ref: Mapped[str | None] = mapped_column(String(50))  # référence fabricant (CAI…)
    designation: Mapped[str] = mapped_column(String(250))
    category: Mapped[str | None] = mapped_column(String(100))  # pièces/accessoires : « Valves »…
    unit: Mapped[str] = mapped_column(String(10), server_default="U")
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(server_default="true")

    brand: Mapped[Brand | None] = relationship(lazy="joined")
    tire: Mapped["TireSpec | None"] = relationship(
        cascade="all, delete-orphan", lazy="joined", uselist=False
    )


class TireSpec(Base):
    """Caractéristiques d'un pneu (une ligne par article de type « pneu »).

    205/55 R16 91 V : largeur 205 mm, hauteur 55 % de la largeur, construction radiale,
    jante 16 pouces, indice de charge 91 (615 kg), indice de vitesse V (240 km/h).
    """

    __tablename__ = "tire_specs"
    __table_args__ = (
        CheckConstraint(_in("vehicle_type", VEHICLE_TYPES), name="vehicle_type"),
        CheckConstraint(_in("season", SEASONS, nullable=True), name="season"),
        CheckConstraint(_in("fuel_class", LABEL_CLASSES, nullable=True), name="fuel_class"),
        CheckConstraint(_in("wet_class", LABEL_CLASSES, nullable=True), name="wet_class"),
        CheckConstraint(_in("noise_class", NOISE_CLASSES, nullable=True), name="noise_class"),
        CheckConstraint("noise_db BETWEEN 50 AND 90", name="noise_db_range"),
        {"schema": "catalog"},
    )

    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("catalog.articles.id", ondelete="CASCADE"), primary_key=True
    )
    vehicle_type: Mapped[str] = mapped_column(String(20))
    season: Mapped[str | None] = mapped_column(String(10))
    width: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))  # 205 ; 31 (pouces) ; 12.5
    aspect_ratio: Mapped[int | None] = mapped_column(Integer)  # 55 (absent = « 80 » implicite)
    construction: Mapped[str | None] = mapped_column(String(2))  # R (radial), D (diagonal), ZR
    rim: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))  # 16 ; 17.5 et 22.5 en poids lourd
    load_index: Mapped[str | None] = mapped_column(String(10))  # 91 ; 154/150 en poids lourd
    speed_index: Mapped[str | None] = mapped_column(String(3))  # V
    # Dimension « compacte » pour la recherche : 205/55 R16 → 2055516.
    size_code: Mapped[str | None] = mapped_column(String(20), index=True)
    reinforced: Mapped[bool] = mapped_column(server_default="false")  # XL / renforcé
    runflat: Mapped[bool] = mapped_column(server_default="false")
    studded: Mapped[bool] = mapped_column(server_default="false")  # clouté
    three_pmsf: Mapped[bool] = mapped_column(server_default="false")  # flocon : vrai pneu hiver
    mud_snow: Mapped[bool] = mapped_column(server_default="false")  # M+S
    # Étiquette européenne (règlement UE 2020/740).
    fuel_class: Mapped[str | None] = mapped_column(String(1))  # résistance au roulement
    wet_class: Mapped[str | None] = mapped_column(String(1))  # adhérence sur sol mouillé
    noise_db: Mapped[int | None] = mapped_column(Integer)
    noise_class: Mapped[str | None] = mapped_column(String(1))
    eprel_id: Mapped[str | None] = mapped_column(String(20))  # fiche de la base européenne EPREL


class ArticleSupplier(Base, BusinessEntity, CompanyScopedMixin):
    """« Cet article, on l'achète chez ce fournisseur, à ce prix. » Propre à la société."""

    __tablename__ = "article_suppliers"
    __table_args__ = (
        UniqueConstraint("company_id", "partner_id", "article_id"),
        Index(
            "uq_article_suppliers_supplier_ref",
            "company_id",
            "partner_id",
            "supplier_ref",
            unique=True,
            postgresql_where=text("supplier_ref IS NOT NULL"),
        ),
        CheckConstraint("purchase_price >= 0", name="purchase_price_positive"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_format"),
        {"schema": "catalog"},
    )

    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("catalog.articles.id"), index=True
    )
    partner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("partners.partners.id"), index=True
    )
    supplier_ref: Mapped[str | None] = mapped_column(String(50))
    # 4 décimales : un prix unitaire de pièce peut valoir 0,0350 €.
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    currency: Mapped[str] = mapped_column(String(3), server_default="EUR")
    is_preferred: Mapped[bool] = mapped_column(server_default="false")
    # Arrêté = le fournisseur ne le propose plus (absent de son dernier tarif complet).
    is_discontinued: Mapped[bool] = mapped_column(server_default="false")
    discontinued_at: Mapped[datetime | None]
    price_updated_at: Mapped[datetime | None]
    last_import_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("catalog.import_runs.id", ondelete="SET NULL")
    )

    article: Mapped[Article] = relationship(lazy="joined")


class ImportProfile(Base, BusinessEntity, CompanyScopedMixin):
    """Comment lire le fichier tarif d'un fournisseur : format et correspondance des colonnes."""

    __tablename__ = "import_profiles"
    __table_args__ = (
        UniqueConstraint("company_id", "partner_id", "name"),
        CheckConstraint("file_format IN ('csv', 'excel')", name="file_format"),
        CheckConstraint(_in("default_kind", KINDS), name="default_kind"),
        CheckConstraint(_in("default_vehicle_type", VEHICLE_TYPES, nullable=True), name="vehicle"),
        CheckConstraint("header_row >= 1", name="header_row_positive"),
        {"schema": "catalog"},
    )

    partner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("partners.partners.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    file_format: Mapped[str] = mapped_column(String(10))
    delimiter: Mapped[str | None] = mapped_column(String(1))  # CSV ; vide = détecté
    encoding: Mapped[str | None] = mapped_column(String(20))  # vide = détecté (UTF-8 ou Windows)
    sheet_name: Mapped[str | None] = mapped_column(String(100))  # Excel ; vide = 1er onglet
    header_row: Mapped[int] = mapped_column(server_default="1")  # ligne des titres de colonnes
    # {"ean": "Code EAN", "purchase_price": "Prix net", …} : champ ERP → titre de colonne.
    mapping: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    # Fichier complet : un article du fournisseur absent du fichier est « arrêté ».
    full_catalog: Mapped[bool] = mapped_column(server_default="true")
    default_kind: Mapped[str] = mapped_column(String(20), server_default="pneu")
    default_vehicle_type: Mapped[str | None] = mapped_column(String(20))
    # Extraire dimension, indices, XL… de la désignation quand il n'y a pas de colonnes.
    parse_designation: Mapped[bool] = mapped_column(server_default="true")


class ImportRun(Base, BusinessEntity, CompanyScopedMixin):
    """Un import de fichier : analyse (aperçu), puis application ou annulation."""

    __tablename__ = "import_runs"
    __table_args__ = (
        CheckConstraint(_in("status", RUN_STATUSES), name="status"),
        CheckConstraint("source IN ('manuel', 'ftp', 'sftp', 'mail')", name="source"),
        {"schema": "catalog"},
    )

    profile_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("catalog.import_profiles.id", ondelete="SET NULL"), index=True
    )
    partner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("partners.partners.id"), index=True
    )
    source: Mapped[str] = mapped_column(String(10), server_default="manuel")
    filename: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(Integer)
    # Le fichier lui-même, en base : le worker (autre conteneur) le relit, et aucun
    # fichier n'est stocké dans un conteneur. `deferred` : chargé seulement si on le lit.
    # Effacé une fois l'import terminé ou annulé.
    content: Mapped[bytes | None] = deferred(mapped_column(LargeBinary))
    status: Mapped[str] = mapped_column(String(20), server_default="analyse")
    full_catalog: Mapped[bool] = mapped_column(server_default="true")
    total_lines: Mapped[int] = mapped_column(server_default="0")
    new_count: Mapped[int] = mapped_column(server_default="0")
    updated_count: Mapped[int] = mapped_column(server_default="0")
    unchanged_count: Mapped[int] = mapped_column(server_default="0")
    reactivated_count: Mapped[int] = mapped_column(server_default="0")
    discontinued_count: Mapped[int] = mapped_column(server_default="0")
    error_count: Mapped[int] = mapped_column(server_default="0")
    active_before: Mapped[int] = mapped_column(server_default="0")  # pour le garde-fou
    message: Mapped[str | None] = mapped_column(Text)
    analyzed_at: Mapped[datetime | None]
    applied_at: Mapped[datetime | None]
    applied_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("auth.users.id"))


class ImportSource(Base, BusinessEntity, CompanyScopedMixin):
    """Relève automatique : où et quand aller chercher le tarif d'un fournisseur."""

    __tablename__ = "import_sources"
    __table_args__ = (
        UniqueConstraint("company_id", "partner_id", "name"),
        CheckConstraint("protocol IN ('sftp', 'ftps', 'ftp')", name="protocol"),
        CheckConstraint("auth_method IN ('password', 'key')", name="auth_method"),
        CheckConstraint("port BETWEEN 1 AND 65535", name="port_range"),
        CheckConstraint("interval_hours BETWEEN 1 AND 168", name="interval_range"),
        CheckConstraint(
            _in("last_status", ("ok", "aucun_fichier", "erreur"), nullable=True), name="last_status"
        ),
        Index("ix_import_sources_due", "next_check_at", postgresql_where=text("is_active")),
        {"schema": "catalog"},
    )

    partner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("partners.partners.id", ondelete="CASCADE"), index=True
    )
    # Le format de colonnes à appliquer (défini lors d'un premier import manuel).
    profile_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("catalog.import_profiles.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(100))
    protocol: Mapped[str] = mapped_column(String(10))
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int]
    username: Mapped[str] = mapped_column(String(100))
    auth_method: Mapped[str] = mapped_column(String(10), server_default="password")
    # Mot de passe ou clé privée SSH, chiffré (app/core/secrets.py). Jamais renvoyé.
    secret: Mapped[str | None] = mapped_column(Text)
    # SFTP : empreinte de la clé du serveur confirmée par l'utilisateur (« ssh-ed25519
    # SHA256:… »). Une autre clé présentée ensuite = connexion refusée.
    host_key: Mapped[str | None] = mapped_column(String(200))
    tls_verify: Mapped[bool] = mapped_column(server_default="true")  # FTPS : certificat vérifié
    remote_dir: Mapped[str] = mapped_column(String(255), server_default="/")
    pattern: Mapped[str] = mapped_column(String(100), server_default="*")  # tarif_*.csv
    interval_hours: Mapped[int] = mapped_column(server_default="24")
    auto_apply: Mapped[bool] = mapped_column(server_default="false")
    is_active: Mapped[bool] = mapped_column(server_default="true")
    next_check_at: Mapped[datetime | None]
    last_check_at: Mapped[datetime | None]
    last_status: Mapped[str | None] = mapped_column(String(20))
    last_message: Mapped[str | None] = mapped_column(Text)
    last_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("catalog.import_runs.id", ondelete="SET NULL")
    )


class ImportSourceFile(Base, IdMixin, CompanyScopedMixin):
    """Fichiers déjà vus sur le serveur du fournisseur : on ne traite pas deux fois le même."""

    __tablename__ = "import_source_files"
    __table_args__ = (
        UniqueConstraint("source_id", "filename", "size", "mtime"),
        CheckConstraint("status IN ('importe', 'ignore')", name="status"),
        {"schema": "catalog"},
    )

    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("catalog.import_sources.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(BigInteger)
    mtime: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(String(10))
    run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("catalog.import_runs.id", ondelete="SET NULL")
    )
    seen_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ImportLine(Base, IdMixin, CompanyScopedMixin):
    """Résultat de l'analyse, ligne par ligne : c'est l'aperçu montré avant d'appliquer."""

    __tablename__ = "import_lines"
    __table_args__ = (
        CheckConstraint(_in("status", LINE_STATUSES), name="status"),
        Index("ix_import_lines_run_status", "run_id", "status"),
        {"schema": "catalog"},
    )

    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("catalog.import_runs.id", ondelete="CASCADE")
    )
    line_no: Mapped[int | None]  # ligne du fichier (vide pour un article arrêté)
    status: Mapped[str] = mapped_column(String(10))
    article_id: Mapped[int | None] = mapped_column(BigInteger)
    link_id: Mapped[int | None] = mapped_column(BigInteger)
    data: Mapped[dict] = mapped_column(JSONB, server_default="{}")  # valeurs lues et normalisées
    old_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    new_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    error: Mapped[str | None] = mapped_column(Text)
