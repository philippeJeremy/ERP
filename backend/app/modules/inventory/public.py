"""Interface publique du module inventory : ce que les autres modules appellent.

- les achats appellent `receive_stock()` à chaque réception ;
- les ventes réservent (`set_reservation`), consultent le disponible (`availability`)
  et sortent le stock à la livraison (`issue_stock`, DOT les plus anciens d'abord).
"""

from app.modules.inventory.service import (
    Availability,
    InsufficientStock,
    IssuedLot,
    availability,
    average_costs,
    ensure_default_location,
    location_codes,
    set_reservation,
)
from app.modules.inventory.service import issue as issue_stock
from app.modules.inventory.service import receive as receive_stock

__all__ = [
    "Availability",
    "InsufficientStock",
    "IssuedLot",
    "availability",
    "average_costs",
    "ensure_default_location",
    "issue_stock",
    "location_codes",
    "receive_stock",
    "set_reservation",
]
