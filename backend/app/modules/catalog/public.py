"""Interface publique du module catalog : ce que les futurs modules (achats, ventes,
stock) importeront pour lire un article ou son prix d'achat."""

from app.modules.catalog.service import get_article

__all__ = ["get_article"]
