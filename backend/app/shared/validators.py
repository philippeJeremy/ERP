"""Contrôles partagés par plusieurs modules."""


def gtin_is_valid(code: str) -> bool:
    """Clé de contrôle des codes GS1 : EAN-8, UPC-12, EAN-13, GTIN-14, et GLN (13 chiffres).

    Poids 3 et 1 en alternance, en partant du chiffre juste avant la clé (modulo 10).
    """
    if not code.isdigit() or len(code) not in (8, 12, 13, 14):
        return False
    body, check = code[:-1], int(code[-1])
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def gln_is_valid(code: str) -> bool:
    """GLN (Global Location Number) : identifiant GS1 d'une entreprise ou d'un lieu,
    13 chiffres. C'est lui qui désigne l'acheteur, le fournisseur et le lieu de
    livraison dans les messages EDI."""
    return len(code) == 13 and gtin_is_valid(code)


def clean_gln(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.replace(" ", "")
    if not value:
        return None
    if not gln_is_valid(value):
        raise ValueError("GLN invalide (13 chiffres, clé de contrôle GS1)")
    return value
