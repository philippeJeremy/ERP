"""Interface publique du module purchasing (pour le futur module stock : réceptions)."""

from app.modules.purchasing.service import get_order

__all__ = ["get_order"]
