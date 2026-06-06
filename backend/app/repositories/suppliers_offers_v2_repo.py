from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import Catalog, Company, CompanyUser, Product, ShippingRate
from app.repositories import product_price_repo
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
    product = Product(
        admin_sku="PENDING",
        catalog_ref=payload.catalog_ref,
        company_tva_intra_com=company_id.strip(),
        client_sku=payload.client_sku,
        product_type=payload.product_type,
        quantity=payload.quantity,
        is_active=payload.is_active,
        teinte=payload.teinte,
        type_de_produit=payload.type_de_produit,
        gamme=payload.gamme,
        duree_garantie=payload.duree_garantie,
        conditions_garantie=payload.conditions_garantie,
        piece_ouvrage_destination=payload.piece_ouvrage_destination,
        traitement_bois_classification=payload.traitement_bois_classification,
        produit_nuance=payload.produit_nuance,
        description_profil=payload.description_profil,
        couleur_traitement_autoclave=payload.couleur_traitement_autoclave,
        code_douane_sh8=payload.code_douane_sh8,
        type_bois=payload.type_bois,
        essence_bois=payload.essence_bois,
        longueur=payload.longueur,
        largeur=payload.largeur,
        hauteur=payload.hauteur,
        volume=payload.volume,
        poids_net=payload.poids_net,
    )
    db.add(product)
    db.flush()
    product.admin_sku = f"ADM-{product.id:08d}"
    product_price_repo.append_price(
        db,
        product_id=product.id,
        price=payload.price,
        currency=payload.currency,
    )
    db.flush()
    return product


def get_product_for_company(
    db: Session, company_id: str, product_id: int
) -> Product | None:
    stmt: Select[tuple[Product]] = select(Product).where(
        Product.id == product_id,
        Product.company_tva_intra_com == company_id.strip(),
    )
    return db.scalar(stmt)


def update_product_fields(
    db: Session, product: Product, payload: ProductUpdateV2
) -> list[str]:
    updates = payload.model_dump(exclude_unset=True)
    price = updates.pop("price", None)
    currency = updates.pop("currency", None)

    for key, value in updates.items():
        setattr(product, key, value)

    changed: list[str] = list(updates.keys())
    if "price" in payload.model_fields_set or "currency" in payload.model_fields_set:
        latest = product_price_repo.get_latest_price(db, product.id)
        new_price = Decimal(
            str(price if price is not None else (latest.price if latest else 0))
        )
        new_currency = (currency or (latest.currency if latest else "EUR")).upper()[:3]
        if latest is None or latest.price != new_price or latest.currency != new_currency:
            product_price_repo.append_price(
                db,
                product_id=product.id,
                price=new_price,
                currency=new_currency,
            )
        if "price" in payload.model_fields_set:
            changed.append("price")
        if "currency" in payload.model_fields_set:
            changed.append("currency")
    return changed
