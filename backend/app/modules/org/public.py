"""Interface publique du module org : la SEULE chose que les autres modules importent.

Exemple : le module facturation appellera `org.next_number(db, "invoice")` à la
validation d'une facture, sans jamais toucher aux tables `org.*` directement.
"""

from app.modules.org.repository import get_company
from app.modules.org.service import next_number

__all__ = ["get_company", "next_number"]
