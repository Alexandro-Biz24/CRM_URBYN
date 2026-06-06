from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.repositories import suppliers_repo
from app.schemas.suppliers import SupplierAccount, SupplierAccountCreate


@dataclass
class SupplierConflictError(Exception):
    field: str
    message: str


def register_supplier(
    db: Session,
    data: SupplierAccountCreate,
) -> SupplierAccount:
    """
    Contrôles : email unique, tva_intra_com unique (PK société).
    """
    existing_user = suppliers_repo.get_user_by_email(db=db, email=str(data.email))
    if existing_user is not None:
        raise SupplierConflictError(
            field="email",
            message="Un utilisateur avec cet email existe déjà.",
        )

    conflict_company = suppliers_repo.get_company_by_tva_intra_com(
        db=db, tva=data.tva_intra_com.strip()
    )
    if conflict_company is not None:
        raise SupplierConflictError(
            field="tva_intra_com",
            message="Une société avec cette TVA intracommunautaire existe déjà.",
        )

    user, company = suppliers_repo.create_supplier_account(db=db, data=data)

    db.commit()
    db.refresh(user)
    db.refresh(company)

    return SupplierAccount(
        user_id=user.id,
        tva_intra_com=company.tva_intra_com,
        email=user.email,
        role_id=user.role_id,
        is_active=user.is_active,
        is_verified=company.is_verified,
    )
