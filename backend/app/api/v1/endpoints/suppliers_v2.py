from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.suppliers_v2 import SupplierAccountCreateV2, SupplierAccountCreatedV2
from app.services.suppliers_v2 import SupplierV2ConflictError, register_supplier_v2


router = APIRouter()


@router.post(
    "/register",
    response_model=SupplierAccountCreatedV2,
    status_code=status.HTTP_201_CREATED,
    summary="Creer un compte fournisseur (V2)",
)
def create_supplier_account_v2(
    payload: SupplierAccountCreateV2,
    db: Session = Depends(get_db),
) -> SupplierAccountCreatedV2:
    """
    Inscription fournisseur V2 avec split de flux:
    - Chemin 1: `existing_company.company_id` fourni -> rattachement a une company existante
    - Chemin 2: `new_company` fourni -> creation company + adresse optionnelle + rattachement

    Tables impactees:
    - users
    - user_profiles
    - companies (chemin 2 uniquement)
    - addresses (chemin 2 si address fournie)
    - companies_users
    """
    try:
        return register_supplier_v2(db=db, payload=payload)
    except SupplierV2ConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"field": exc.field, "message": exc.message},
        ) from exc

