from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import Catalog, CatalogProduct, Company, CompanyUser, Product, ShippingRate
from app.repositories import product_price_repo
from app.repositories import supplier_portal_repo as portal_repo
from app.schemas.suppliers_offers_v2 import (
    CatalogCreateV2,
    ProductCreateV2,
    ProductUpdateV2,
    ShippingRateCreateV2,
)


def get_company(db: Session, company_id: str) -> Company | None:
    stmt: Select[tuple[Company]] = select(Company).where(
        Company.tva_intra_com == company_id.strip()
    )
    return db.scalar(stmt)


def get_latest_company_id_for_user(db: Session, user_id: int) -> str | None:
    stmt = (
        select(CompanyUser.company_tva_intra_com)
        .where(CompanyUser.user_id == user_id)
        .order_by(CompanyUser.id.desc())
    )
    return db.scalar(stmt)


def create_shipping_rate(db: Session, payload: ShippingRateCreateV2) -> ShippingRate:
    rate = ShippingRate(
        company_tva_intra_com=payload.company_id.strip(),
        carrier_name=payload.carrier_name,
        zone_from=payload.zone_from,
        zone_to=payload.zone_to,
        weight_min_kg=payload.weight_min_kg,
        weight_max_kg=payload.weight_max_kg,
        volume_max_m3=payload.volume_max_m3,
        rate_per_kg=payload.rate_per_kg,
        base_rate=payload.base_rate,
        currency=payload.currency,
        is_active=payload.is_active,
    )
    db.add(rate)
    db.flush()
    return rate


def get_catalog(db: Session, catalog_id: int) -> Catalog | None:
    return db.get(Catalog, catalog_id)


def create_catalog(db: Session, payload: CatalogCreateV2) -> Catalog:
    catalog = Catalog(
        parent_id=payload.parent_id,
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
    )
    db.add(catalog)
    db.flush()
    if catalog.parent_id is None:
        catalog.parent_id = catalog.id
        db.flush()
    return catalog


def create_product(
    db: Session,
    company_id: str,
    payload: ProductCreateV2,
) -> Product:
    from app.schemas.supplier_portal import MandatoryAttributeValueWrite, PortalSession, ProductWrite

    write = ProductWrite(
        session=PortalSession(user_id=0, email="api@v2.local"),
        primary_catalog_id=payload.primary_catalog_id,
        additional_catalog_ids=payload.additional_catalog_ids,
        client_sku=payload.client_sku,
        product_name=payload.product_name,
        price=payload.price,
        currency=payload.currency,
        is_active=payload.is_active,
        mandatory_attributes=[
            MandatoryAttributeValueWrite(definition_id=m.definition_id, value=m.value)
            for m in payload.mandatory_attributes
        ],
    )
    return portal_repo.create_product(db, company_id, write)


def get_product_for_company(
    db: Session, company_id: str, product_id: int
) -> Product | None:
    stmt: Select[tuple[Product]] = select(Product).where(
        Product.id == product_id,
        Product.company_tva_intra_com == company_id.strip(),
    )
    return db.scalar(stmt)


def get_product_primary_catalog_id(db: Session, product_id: int) -> int | None:
    ids = portal_repo.get_product_catalog_ids(db, product_id)
    return ids[0] if ids else None


def update_product_fields(
    db: Session, product: Product, payload: ProductUpdateV2
) -> list[str]:
    from app.schemas.supplier_portal import MandatoryAttributeValueWrite, ProductWrite

    changed: list[str] = []
    updates = payload.model_dump(exclude_unset=True)

    primary = updates.pop("primary_catalog_id", None)
    additional = updates.pop("additional_catalog_ids", None)
    mandatory = updates.pop("mandatory_attributes", None)
    price = updates.pop("price", None)
    currency = updates.pop("currency", None)

    for key, value in updates.items():
        if hasattr(product, key):
            setattr(product, key, value)
            changed.append(key)

    catalog_ids = portal_repo.get_product_catalog_ids(db, product.id)
    primary_id = primary if primary is not None else (catalog_ids[0] if catalog_ids else None)
    if primary_id is None:
        return changed

    additional_ids = (
        additional if additional is not None else [c for c in catalog_ids if c != primary_id]
    )

    if primary is not None or additional is not None:
        portal_repo.sync_catalog_products(
            db, product.id, [primary_id, *additional_ids]
        )
        changed.extend(["primary_catalog_id", "additional_catalog_ids"])

    if mandatory is not None:
        portal_repo.sync_mandatory_attributes(
            db,
            product.id,
            [
                MandatoryAttributeValueWrite(definition_id=m["definition_id"], value=m["value"])
                for m in mandatory
            ],
        )
        changed.append("mandatory_attributes")

    if price is not None or currency is not None:
        latest = product_price_repo.get_latest_price(db, product.id)
        new_price = Decimal(str(price if price is not None else (latest.price if latest else 0)))
        new_currency = (currency or (latest.currency if latest else "EUR")).upper()[:3]
        if latest is None or latest.price != new_price or latest.currency != new_currency:
            product_price_repo.append_price(
                db,
                product_id=product.id,
                price=new_price,
                currency=new_currency,
            )
        if price is not None:
            changed.append("price")
        if currency is not None:
            changed.append("currency")

    return changed
