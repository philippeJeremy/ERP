"""Modèles de mail par défaut. Chaque société peut les modifier (table mail.templates).

Les champs entre accolades sont remplacés à l'envoi : {numero}, {montant_ttc}…
Un champ inconnu est laissé tel quel (pas d'erreur).
"""

LABELS = {
    "devis": "Envoi d'un devis",
    "facture": "Envoi d'une facture",
    "avoir": "Envoi d'un avoir",
    "relance": "Relance de factures impayées",
    "commande_fournisseur": "Envoi d'un bon de commande fournisseur",
}

FIELDS = {
    "devis": [
        "numero",
        "date",
        "validite",
        "montant_ttc",
        "destinataire",
        "reference",
        "societe",
        "signature",
    ],
    "facture": [
        "numero",
        "date",
        "echeance",
        "montant_ttc",
        "destinataire",
        "reference",
        "societe",
        "signature",
    ],
    "avoir": ["numero", "date", "montant_ttc", "facture", "destinataire", "societe", "signature"],
    "relance": ["destinataire", "factures", "total_du", "niveau", "societe", "signature"],
    "commande_fournisseur": [
        "numero",
        "date",
        "livraison",
        "depot",
        "destinataire",
        "societe",
        "signature",
    ],
}

DEFAULTS = {
    "devis": (
        "Devis {numero} — {societe}",
        "Bonjour,\n\nVeuillez trouver ci-joint notre devis {numero} du {date}, d'un montant de "
        "{montant_ttc} TTC, valable jusqu'au {validite}.\n\nPour l'accepter, il vous suffit de "
        "nous le retourner signé ou de répondre à ce message.\n\nNous restons à votre disposition "
        "pour toute question.\n\nCordialement,\n{signature}\n{societe}",
    ),
    "facture": (
        "Facture {numero} — {societe}",
        "Bonjour,\n\nVeuillez trouver ci-joint notre facture {numero} du {date}, d'un montant de "
        "{montant_ttc} TTC, payable au plus tard le {echeance}.\n\nLe fichier PDF est au format "
        "Factur-X : il contient aussi les données de la facture pour votre logiciel "
        "comptable.\n\nCordialement,\n{signature}\n{societe}",
    ),
    "avoir": (
        "Avoir {numero} — {societe}",
        "Bonjour,\n\nVeuillez trouver ci-joint notre avoir {numero} du {date}, d'un montant de "
        "{montant_ttc} TTC, sur la facture {facture}.\n\nCordialement,\n{signature}\n{societe}",
    ),
    "relance": (
        "{niveau} — factures en attente de règlement",
        "Bonjour,\n\nSauf erreur de notre part, les factures suivantes restent impayées :\n\n"
        "{factures}\n\nTotal dû : {total_du}.\n\nMerci de bien vouloir procéder à leur règlement. "
        "Si votre paiement a été émis entre-temps, merci de ne pas tenir compte de ce "
        "message.\n\nLe détail figure dans le courrier joint.\n\nCordialement,\n{signature}\n"
        "{societe}",
    ),
    "commande_fournisseur": (
        "Commande {numero} — {societe}",
        "Bonjour,\n\nVeuillez trouver ci-joint notre bon de commande {numero} du {date}, à livrer "
        "à notre dépôt {depot}{livraison}.\n\nMerci de nous en accuser réception et de nous "
        "confirmer le délai de livraison.\n\nCordialement,\n{signature}\n{societe}",
    ),
}


class _Keep(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render(text: str, values: dict[str, str]) -> str:
    try:
        return text.format_map(_Keep(values))
    except (ValueError, IndexError):  # accolade isolée dans le texte : on n'y touche pas
        return text


def euros(value) -> str:
    """1234.5 → « 1 234,50 € » (espaces insécables)."""
    return f"{value:,.2f}".replace(",", "\u202f").replace(".", ",") + "\u00a0€"


def fdate(value) -> str:
    return value.strftime("%d/%m/%Y") if value else ""
