from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.suppliers import SupplierAccount, SupplierAccountCreate
from app.services.suppliers import SupplierConflictError, register_supplier


router = APIRouter()


@router.post(
    "/register",
    response_model=SupplierAccount,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un compte fournisseur",
)
def create_supplier_account(
    payload: SupplierAccountCreate,
    db: Session = Depends(get_db),
) -> SupplierAccount:
    """
    Crée un **compte fournisseur complet** dans la base.

    Cette route :
    - utilisateur (`users`, `role_id` → **Fournisseur** si présent en base)
    - profil (`user_profiles`)
    - société (`companies`, PK **tva_intra_com**)
    - liaison (`companies_users`)
    - optionnel : `addresses`

    Contraintes : email unique, **tva_intra_com** unique.
    """
    try:
        account = register_supplier(db=db, data=payload)
    except SupplierConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"field": exc.field, "message": exc.message},
        ) from exc

    return account

