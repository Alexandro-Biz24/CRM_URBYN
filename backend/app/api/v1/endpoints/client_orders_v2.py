"""
Checkout client : création commande (`orders` + `product_order`) depuis un panier produits.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.client_orders_v2 import ClientCheckoutCreateV2, ClientCheckoutCreatedV2
from app.services.client_orders_v2 import ClientOrderV2Error, checkout_client_v2


router = APIRouter()


@router.post(
    "/checkout",
    response_model=ClientCheckoutCreatedV2,
    status_code=status.HTTP_201_CREATED,
    summary="Valider le panier et creer la commande",
)
def client_checkout(
    payload: ClientCheckoutCreateV2,
    db: Session = Depends(get_db),
) -> ClientCheckoutCreatedV2:
    """
    Crée une ou plusieurs commandes marketplace (une **par fournisseur** / TVA).

    - **buyer_id** : user avec rôle **Client**
    - **items** : lignes `product_id` + `quantity` (panier multi-fournisseurs autorisé)

    Pour chaque produit : TVA = `products.companies_id`. Frais / TVA globaux répartis **au prorata**
    du sous-total par fournisseur. Le vendeur n’est pas exposé ni résolu pour l’instant.

    Prix unitaire : dernière entrée de `product_price_history` pour chaque `product_id`.
    `product_order.catalog_id` fige le catalogue au moment de la commande.

    Si `decrement_stock` est True, décrémente `products.quantity`.
    """
    try:
        return checkout_client_v2(db=db, payload=payload)
    except ClientOrderV2Error as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"field": exc.field, "message": exc.message},
        ) from exc
