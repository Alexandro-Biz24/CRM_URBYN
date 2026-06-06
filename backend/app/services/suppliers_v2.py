from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.repositories import suppliers_v2_repo
from app.schemas.suppliers_v2 import SupplierAccountCreateV2, SupplierAccountCreatedV2


@dataclass
class SupplierV2ConflictError(Exception):
    field: str
    message: str


def _resolve_target_company(payload: SupplierAccountCreateV2) -> tuple[str, bool]:
    has_existing = payload.existing_company is not None
    has_new = payload.new_company is not None

    if has_existing == has_new:
        raise SupplierV2ConflictError(
            field="company",
            message=(
                "Tu dois fournir exactement un seul chemin: existing_company OU new_company."
            ),
        )

    if has_existing:
        return payload.existing_company.company_id.strip(), False  # type: ignore[union-attr]
    return payload.new_company.tva_intra_com.strip(), True  # type: ignore[union-attr]


def register_supplier_v2(db: Session, payload: SupplierAccountCreateV2) -> SupplierAccountCreatedV2:
    supplier_role_id = suppliers_v2_repo.get_supplier_role_id(db=db)
    if supplier_role_id is None:
        raise SupplierV2ConflictError(
            field="role",
            message=(
                "Le role 'Fournisseur' est introuvable dans la table roles. "
                "Ajoute-le avant de creer des comptes fournisseur."
            ),
        )

    existing_user = suppliers_v2_repo.get_user_by_email(db=db, email=str(payload.email))
    if existing_user is not None:
        raise SupplierV2ConflictError(
            field="email",
            message="Un utilisateur avec cet email existe deja.",
        )

    if not suppliers_v2_repo.language_exists(db=db, language_id=payload.language_id):
        raise SupplierV2ConflictError(
            field="language_id",
            message=(
                f"La langue {payload.language_id} est introuvable dans languages. "
                "Ajoute-la d'abord puis retente."
            ),
        )

    target_company_tva, create_company_flag = _resolve_target_company(payload)

    existing_company = suppliers_v2_repo.get_company_by_tva(
        db=db, company_tva_intra_com=target_company_tva
    )

    if create_company_flag and existing_company is not None:
        raise SupplierV2ConflictError(
            field="new_company.tva_intra_com",
            message="Cette company existe deja. Utilise existing_company.company_id.",
        )

    if not create_company_flag and existing_company is None:
        raise SupplierV2ConflictError(
            field="existing_company.company_id",
            message="Company introuvable avec cet identifiant.",
        )

    user = suppliers_v2_repo.create_user(db=db, payload=payload, role_id=supplier_role_id)
    suppliers_v2_repo.create_user_profile(db=db, user_id=user.id, payload=payload)

    if create_company_flag:
        company = suppliers_v2_repo.create_company(db=db, payload=payload.new_company)  # type: ignore[arg-type]
        if payload.new_company and payload.new_company.address is not None:
            suppliers_v2_repo.create_company_address(
                db=db,
                company_tva_intra_com=company.tva_intra_com,
                address=payload.new_company.address,
            )
        company_tva = company.tva_intra_com
    else:
        company_tva = target_company_tva

    suppliers_v2_repo.create_company_membership(
        db=db,
        user_id=user.id,
        company_tva_intra_com=company_tva,
    )

    db.commit()
    db.refresh(user)

    return SupplierAccountCreatedV2(
        user_id=user.id,
        role_id=user.role_id,
        company_id=company_tva,
        email=user.email,
        is_active=user.is_active,
        company_created=create_company_flag,
    )

