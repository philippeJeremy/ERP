"""Interface publique du module inventory : ce que les autres modules appellent.

Les achats appellent `receive_stock()` à chaque réception ; demain les ventes
appelleront une sortie de stock, toujours par ici.
"""

from app.modules.inventory.service import InsufficientStock, ensure_default_location
from app.modules.inventory.service import receive as receive_stock

__all__ = ["InsufficientStock", "ensure_default_location", "receive_stock"]
