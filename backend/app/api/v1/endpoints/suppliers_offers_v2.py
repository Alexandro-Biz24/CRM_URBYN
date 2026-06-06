from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.suppliers_offers_v2 import (
    ProductUpdateV2,
    ProductUpdatedV2,
    ShippingRateCreateV2,
    ShippingRateCreatedV2,
    SupplierOfferCreateV2,
    SupplierOfferCreatedV2,
)
from app.services.suppliers_offers_v2 import (
    SupplierOfferV2Error,
    create_shipping_rate_v2,
    create_supplier_offer_v2,
    update_product_v2,
)

router = APIRouter()


@router.post(
    "/shipping-rates",
    response_model=ShippingRateCreatedV2,
    status_code=status.HTTP_201_CREATED,
    summary="Creer un tarif de livraison fournisseur",
)
def create_shipping_rate(
    payload: ShippingRateCreateV2,
    db: Session = Depends(get_db),
) -> ShippingRateCreatedV2:
    try:
        return create_shipping_rate_v2(db=db, payload=payload)
    except SupplierOfferV2Error as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"field": exc.field, "message": exc.message},
        ) from exc


@router.post(
    "/offers",
    response_model=SupplierOfferCreatedV2,
    status_code=status.HTTP_201_CREATED,
    summary="Creer un produit (catalogue existant ou nouveau)",
)
def create_supplier_offer(
    payload: SupplierOfferCreateV2,
    db: Session = Depends(get_db),
) -> SupplierOfferCreatedV2:
    try:
        return create_supplier_offer_v2(db=db, payload=payload)
    except SupplierOfferV2Error as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"field": exc.field, "message": exc.message},
        ) from exc


@router.patch(
    "/products/{company_id}/{product_id}",
    response_model=ProductUpdatedV2,
    summary="Mettre a jour un produit fournisseur",
)
def update_product(
    company_id: str,
    product_id: int,
    payload: ProductUpdateV2,
    db: Session = Depends(get_db),
) -> ProductUpdatedV2:
    try:
        updated_fields = update_product_v2(
            db=db,
            company_id=company_id,
            product_id=product_id,
            payload=payload,
        )
    except SupplierOfferV2Error as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"field": exc.field, "message": exc.message},
        ) from exc
    return ProductUpdatedV2(
        company_id=company_id,
        product_id=product_id,
        updated_fields=updated_fields,
    )
