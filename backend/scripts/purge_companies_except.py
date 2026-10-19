"""Supprime toutes les sociétés sauf celles gardées (par TVA).

Par défaut : simulation (purge exécutée dans une transaction puis rollback),
avec le nombre de lignes supprimées par table. `--apply` pour valider.

Usage :
    python -m scripts.purge_companies_except --keep FR73827458779
    python -m scripts.purge_companies_except --keep FR73827458779 --apply
"""

from __future__ import annotations

import argparse

from sqlalchemy import delete, func, select

from app.db.base import Base
from app.db.session import SessionLocal
from app.models import Company, CompanyUser, User
from app.repositories import admin_accounts_repo


def _table_counts(db) -> dict[str, int]:
    return {
        name: int(db.scalar(select(func.count()).select_from(table)) or 0)
        for name, table in sorted(Base.metadata.tables.items())
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", nargs="+", required=True, help="TVA des sociétés à garder")
    parser.add_argument("--apply", action="store_true", help="Valide la purge (sinon rollback)")
    args = parser.parse_args()
    keep = {tva.strip() for tva in args.keep}

    db = SessionLocal()
    try:
        missing = [tva for tva in keep if db.get(Company, tva) is None]
        if missing:
            raise SystemExit(f"Société(s) à garder introuvable(s) : {', '.join(missing)}")

        # Users rattachés aussi à une société gardée : on coupe seulement le lien
        protected_user_ids = set(
            db.scalars(
                select(CompanyUser.user_id).where(CompanyUser.company_tva_intra_com.in_(keep))
            ).all()
        )

        to_delete = db.scalars(
            select(Company).where(Company.tva_intra_com.notin_(keep)).order_by(Company.company_name)
        ).all()
        print(f"Sociétés gardées : {sorted(keep)}")
        print(f"Sociétés à supprimer : {len(to_delete)}")

        before = _table_counts(db)
        deleted_users: list[str] = []
        for company in to_delete:
            tva = company.tva_intra_com
            if protected_user_ids:
                db.execute(
                    delete(CompanyUser).where(
                        CompanyUser.company_tva_intra_com == tva,
                        CompanyUser.user_id.in_(protected_user_ids),
                    )
                )
            user_ids = db.scalars(
                select(CompanyUser.user_id).where(CompanyUser.company_tva_intra_com == tva)
            ).all()
            for user in db.scalars(select(User).where(User.id.in_(user_ids))).all():
                deleted_users.append(f"{user.id} {user.email} ({company.company_name})")
            admin_accounts_repo.delete_company(db, tva)
        db.flush()
        after = _table_counts(db)

        print("\nLignes supprimées par table :")
        for name, count in before.items():
            diff = count - after.get(name, 0)
            if diff:
                print(f"  {name:40} -{diff}  (reste {after[name]})")

        print(f"\nUtilisateurs supprimés : {len(deleted_users)}")
        for line in deleted_users:
            print(f"  {line}")
        print(f"Utilisateurs protégés (liés à une société gardée) : {sorted(protected_user_ids)}")

        if args.apply:
            db.commit()
            print("\nPURGE VALIDÉE.")
        else:
            db.rollback()
            print("\nSIMULATION — rien n'a été modifié (relancer avec --apply).")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
