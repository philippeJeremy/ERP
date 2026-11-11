"""Bases Pydantic communes."""

from pydantic import BaseModel, ConfigDict


class Schema(BaseModel):
    """Schéma d'entrée : refuse les champs inconnus (évite les fautes de frappe silencieuses)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReadSchema(BaseModel):
    """Schéma de sortie : se construit directement depuis un objet SQLAlchemy."""

    model_config = ConfigDict(from_attributes=True)
