"""
Inscription client V2 : même logique que fournisseur V2 (company existante ou nouvelle).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.clients_v2 import ClientAccountCreateV2, ClientAccountCreatedV2
from app.services.clients_v2 import ClientV2ConflictError, register_client_v2


router = APIRouter()


@router.post(
    "/register",
    response_model=ClientAccountCreatedV2,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un compte client entreprise (V2)",
)
def create_client_account_v2(
    payload: ClientAccountCreateV2,
    db: Session = Depends(get_db),
) -> ClientAccountCreatedV2:
    """
    Inscription **client** (entreprise) V2.

    - `users` avec rôle **Client** (résolu par nom `Client` dans `roles`, typiquement id=3)
    - `user_profiles`
    - soit rattachement à une `companies` existante (`existing_company.company_id` = TVA),
    - soit création `companies` + `addresses` optionnelle + liaison `companies_users`

    Même modèle société que le fournisseur ; la distinction métier viendra plus tard
    (commandes, stats, etc.).
    """
    try:
        return register_client_v2(db=db, payload=payload)
    except ClientV2ConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"field": exc.field, "message": exc.message},
        ) from exc
