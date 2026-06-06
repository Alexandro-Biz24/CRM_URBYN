"""
Routes API dédiées aux comptes client (inscription, etc.).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.clients import ClientAccount, ClientAccountCreate
from app.services.clients import ClientConflictError, register_client


router = APIRouter()


@router.post(
    "/register",
    response_model=ClientAccount,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un compte client",
)
def create_client_account(
    payload: ClientAccountCreate,
    db: Session = Depends(get_db),
) -> ClientAccount:
    """
    Crée un **compte client** dans la base.

    - Crée l'utilisateur (`users`, `role_id` → rôle **client** si présent en base)
    - Profil (`user_profiles`) : langue, titre, prénom, nom
    - Société (`companies`, PK **tva_intra_com**, raison sociale + champs DEMANDE)
    - Liaison (`companies_users`)
    - Optionnel : `addresses` (SIRET / intra_communal possibles)

    Contraintes : email unique, **tva_intra_com** unique.
    """
    try:
        account = register_client(db=db, data=payload)
    except ClientConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"field": exc.field, "message": exc.message},
        ) from exc
    return account
