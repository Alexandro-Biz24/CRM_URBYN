from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.repositories import suppliers_offers_v2_repo
from app.schemas.suppliers_offers_v2 import (
    ProductUpdateV2,
    ShippingRateCreateV2,
    ShippingRateCreatedV2,
    SupplierOfferCreateV2,
    SupplierOfferCreatedV2,
    ProductUpdatedV2,
)


@dataclass
class SupplierOfferV2Error(Exception):
    field: str
    message: str


def _resolve_company_id(db: Session, company_id: str | None, user_id: int | None) -> str:
    if company_id is not None and company_id.strip():
        return company_id.strip()
    if user_id is not None:
        resolved = suppliers_offers_v2_repo.get_latest_company_id_for_user(
            db=db, user_id=user_id
        )
        if resolved is not None:
            return resolved
    raise SupplierOfferV2Error(
        field="company_id",
        message="Fournis company_id ou user_id rattache a une company.",
    )


def create_shipping_rate_v2(
    db: Session, payload: ShippingRateCreateV2
) -> ShippingRateCreatedV2:
    resolved_company_id = _resolve_company_id(
        db=db, company_id=payload.company_id, user_id=payload.user_id
    )
    company = suppliers_offers_v2_repo.get_company(db=db, company_id=resolved_company_id)
    if company is None:
        raise SupplierOfferV2Error(
            field="company_id",
            message="Company introuvable pour ce shipping rate.",
        )

    payload_to_create = payload.model_copy(update={"company_id": resolved_company_id})
    rate = suppliers_offers_v2_repo.create_shipping_rate(db=db, payload=payload_to_create)
    db.commit()
    db.refresh(rate)
    return ShippingRateCreatedV2(id=rate.id, company_id=rate.company_tva_intra_com)


def create_supplier_offer_v2(
    db: Session, payload: SupplierOfferCreateV2
) -> SupplierOfferCreatedV2:
    resolved_company_id = _resolve_company_id(
        db=db, company_id=payload.company_id, user_id=payload.user_id
    )
    company = suppliers_offers_v2_repo.get_company(db=db, company_id=resolved_company_id)
    if company is None:
        raise SupplierOfferV2Error(
            field="company_id",
            message="Company introuvable pour la creation de l'offre.",
        )

    catalog_ref = payload.catalog_ref
    if payload.catalog is not None:
        catalog = suppliers_offers_v2_repo.create_catalog(db=db, payload=payload.catalog)
        catalog_ref = catalog.id
    if catalog_ref is None:
        raise SupplierOfferV2Error(
            field="catalog_ref",
            message="Fournis catalog_ref ou un bloc catalog a creer.",
        )
    if suppliers_offers_v2_repo.get_catalog(db, catalog_ref) is None:
        raise SupplierOfferV2Error(
            field="catalog_ref",
            message="Catalogue introuvable.",
        )

    product_payload = payload.product.model_copy(update={"catalog_ref": catalog_ref})
    product = suppliers_offers_v2_repo.create_product(
        db=db,
        company_id=resolved_company_id,
        payload=product_payload,
    )
    db.commit()
    db.refresh(product)
    return SupplierOfferCreatedV2(
        catalog_id=catalog_ref,
        product_id=product.id,
        admin_sku=product.admin_sku,
        company_id=resolved_company_id,
    )


def update_product_v2(
    db: Session,
    company_id: str,
    product_id: int,
    payload: ProductUpdateV2,
) -> list[str]:
    product = suppliers_offers_v2_repo.get_product_for_company(
        db=db,
        company_id=company_id,
        product_id=product_id,
    )
    if product is None:
        raise SupplierOfferV2Error(
            field="product",
            message="Produit introuvable pour cette société.",
        )

    if not payload.model_dump(exclude_unset=True):
        raise SupplierOfferV2Error(
            field="payload",
            message="Aucun champ a mettre a jour.",
        )

    if payload.catalog_ref is not None:
        if suppliers_offers_v2_repo.get_catalog(db, payload.catalog_ref) is None:
            raise SupplierOfferV2Error(
                field="catalog_ref",
                message="Catalogue introuvable.",
            )

    updated_fields = suppliers_offers_v2_repo.update_product_fields(
        db=db, product=product, payload=payload
    )
    db.commit()
    return updated_fields
