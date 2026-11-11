"""Commandes d'administration.

Créer le premier super-administrateur et la première société (une seule fois) :
    docker compose run --rm api python -m app.cli bootstrap \
        --email admin@exemple.fr --name "Admin" --company-code HOLD --company-name "Ma Holding"
Le mot de passe est demandé au clavier (jamais en argument : il finirait dans l'historique).
"""

import argparse
import getpass
import sys

from app import modules
from app.core.context import RequestContext
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.modules.auth import repository as auth_repo
from app.modules.auth.models import User
from app.modules.org import service as org_service
from app.modules.org.schemas import CompanyCreate


def bootstrap(args: argparse.Namespace) -> int:
    password = getpass.getpass("Mot de passe (12 caractères minimum) : ")
    if len(password) < 12 or password != getpass.getpass("Confirmation : "):
        print("Mot de passe trop court ou confirmation différente.", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        if auth_repo.get_user_by_email(db, args.email):
            print(f"Le compte {args.email} existe déjà.", file=sys.stderr)
            return 1
        user = User(
            email=args.email,
            full_name=args.name,
            password_hash=hash_password(password),
            is_superuser=True,
        )
        db.add(user)
        db.commit()

        ctx = RequestContext(user_id=user.id, is_superuser=True)
        company = org_service.create_company(
            db, ctx, CompanyCreate(code=args.company_code, name=args.company_name)
        )
        print(f"Super-administrateur #{user.id} et société #{company.id} ({company.code}) créés.")
    return 0


def main() -> int:
    modules.load_models()
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("bootstrap", help="Premier super-admin + première société")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--company-code", required=True)
    p.add_argument("--company-name", required=True)
    args = parser.parse_args()
    return {"bootstrap": bootstrap}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
