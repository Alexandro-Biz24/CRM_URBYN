from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Catalog,
    CatalogAttributeDefinition,
    CatalogLink,
    CatalogProduct,
    Company,
    CompanyUser,
    Product,
    ProductAttribut,
    ProductMandatoryAttributeValue,
    Role,
    User,
)
from app.repositories import product_price_repo
from app.schemas.supplier_portal import (
    CatalogUpdateBody,
    CatalogWrite,
    MandatoryAttributeValueWrite,
    ProductAttributWrite,
    ProductWrite,
)


def get_user(db: Session, user_id: int, email: str) -> User | None:
    normalized = email.strip().lower()
    stmt = (
        select(User)
        .options(joinedload(User.role))
        .where(User.id == user_id, func.lower(User.email) == normalized)
    )
    return db.scalar(stmt)


def get_company_for_user(db: Session, user_id: int) -> tuple[str, str] | None:
    stmt = (
        select(Company.tva_intra_com, Company.company_name)
        .join(CompanyUser, CompanyUser.company_tva_intra_com == Company.tva_intra_com)
        .where(CompanyUser.user_id == user_id)
        .order_by(CompanyUser.id.desc())
        .limit(1)
    )
    row = db.execute(stmt).first()
    return (row[0], row[1]) if row else None


def list_catalogs(db: Session) -> list[Catalog]:
    stmt = select(Catalog).order_by(Catalog.name)
    return list(db.scalars(stmt).all())


def list_root_catalogs(db: Session) -> list[Catalog]:
    stmt = (
        select(Catalog)
        .where((Catalog.parent_id == Catalog.id) | (Catalog.parent_id.is_(None)))
        .order_by(Catalog.name)
    )
    return list(db.scalars(stmt).all())


def list_catalog_children(db: Session, parent_id: int) -> list[Catalog]:
    stmt = (
        select(Catalog)
        .where(Catalog.parent_id == parent_id, Catalog.id != parent_id)
        .order_by(Catalog.name)
    )
    return list(db.scalars(stmt).all())


def search_catalogs(db: Session, query: str, limit: int = 30) -> list[Catalog]:
    q = query.strip()
    if not q:
        return []
    pattern = f"%{q}%"
    stmt = (
        select(Catalog)
        .where(
            Catalog.is_active.is_(True),
            (Catalog.name.ilike(pattern)) | (Catalog.description.ilike(pattern)),
        )
        .order_by(Catalog.name)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def get_catalog(db: Session, catalog_id: int) -> Catalog | None:
    return db.get(Catalog, catalog_id)


def _is_root(catalog: Catalog) -> bool:
    return catalog.parent_id is None or catalog.parent_id == catalog.id


def get_breadcrumb(db: Session, catalog: Catalog) -> list[str]:
    names: list[str] = []
    current: Catalog | None = catalog
    seen: set[int] = set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        if current.name:
            names.append(current.name)
        if _is_root(current):
            break
        parent = db.get(Catalog, current.parent_id) if current.parent_id else None
        current = parent
    names.reverse()
    return names


def list_catalog_attribute_definitions(
    db: Session, catalog_id: int
) -> list[CatalogAttributeDefinition]:
    stmt = (
        select(CatalogAttributeDefinition)
        .where(CatalogAttributeDefinition.catalog_id == catalog_id)
        .order_by(CatalogAttributeDefinition.attribute_name)
    )
    return list(db.scalars(stmt).all())


def list_attribute_definitions_for_catalogs(
    db: Session, catalog_ids: list[int]
) -> list[CatalogAttributeDefinition]:
    if not catalog_ids:
        return []
    stmt = (
        select(CatalogAttributeDefinition)
        .where(CatalogAttributeDefinition.catalog_id.in_(catalog_ids))
        .order_by(CatalogAttributeDefinition.catalog_id, CatalogAttributeDefinition.attribute_name)
    )
    return list(db.scalars(stmt).all())


def create_catalog(db: Session, data: CatalogWrite) -> Catalog:
    catalog = Catalog(
        parent_id=data.parent_id,
        name=data.name.strip(),
        description=data.description.strip(),
        is_active=data.is_active,
    )
    db.add(catalog)
    db.flush()
    if catalog.parent_id is None:
        catalog.parent_id = catalog.id
        db.flush()
    return catalog


def update_catalog(db: Session, catalog: Catalog, data: CatalogUpdateBody) -> Catalog:
    catalog.name = data.name.strip()
    catalog.description = data.description.strip()
    catalog.is_active = data.is_active
    if data.parent_id is not None:
        catalog.parent_id = data.parent_id
    catalog.updated_at = datetime.utcnow()
    db.flush()
    return catalog


def get_product_catalog_ids(db: Session, product_id: int) -> list[int]:
    stmt = select(CatalogProduct.catalog_id).where(CatalogProduct.product_id == product_id)
    return list(db.scalars(stmt).all())


def sync_catalog_products(db: Session, product_id: int, catalog_ids: list[int]) -> None:
    unique_ids = list(dict.fromkeys(catalog_ids))
    existing = set(get_product_catalog_ids(db, product_id))
    target = set(unique_ids)
    for cid in target - existing:
        db.add(CatalogProduct(catalog_id=cid, product_id=product_id))
    for cid in existing - target:
        db.execute(
            delete(CatalogProduct).where(
                CatalogProduct.product_id == product_id,
                CatalogProduct.catalog_id == cid,
            )
        )
    db.flush()


def ensure_catalog_links(db: Session, from_catalog_id: int, to_catalog_ids: list[int]) -> None:
    for to_id in to_catalog_ids:
        if to_id == from_catalog_id:
            continue
        exists = db.scalar(
            select(CatalogLink.id).where(
                CatalogLink.from_catalog_id == from_catalog_id,
                CatalogLink.to_catalog_id == to_id,
            )
        )
        if exists is None:
            db.add(CatalogLink(from_catalog_id=from_catalog_id, to_catalog_id=to_id))
    db.flush()


def sync_mandatory_attributes(
    db: Session,
    product_id: int,
    values: list[MandatoryAttributeValueWrite],
) -> None:
    by_def = {v.definition_id: v.value.strip() for v in values}
    existing = list(
        db.scalars(
            select(ProductMandatoryAttributeValue).where(
                ProductMandatoryAttributeValue.product_id == product_id
            )
        ).all()
    )
    seen_defs: set[int] = set()
    for row in existing:
        if row.catalog_attribute_definition_id in by_def:
            row.value = by_def[row.catalog_attribute_definition_id]
            row.updated_at = datetime.utcnow()
            seen_defs.add(row.catalog_attribute_definition_id)
        else:
            db.delete(row)
    for def_id, val in by_def.items():
        if def_id in seen_defs:
            continue
        db.add(
            ProductMandatoryAttributeValue(
                product_id=product_id,
                catalog_attribute_definition_id=def_id,
                value=val,
            )
        )
    db.flush()


def list_mandatory_attribute_values(
    db: Session, product_id: int
) -> list[tuple[ProductMandatoryAttributeValue, CatalogAttributeDefinition]]:
    stmt = (
        select(ProductMandatoryAttributeValue, CatalogAttributeDefinition)
        .join(
            CatalogAttributeDefinition,
            CatalogAttributeDefinition.id
            == ProductMandatoryAttributeValue.catalog_attribute_definition_id,
        )
        .where(ProductMandatoryAttributeValue.product_id == product_id)
        .order_by(CatalogAttributeDefinition.catalog_id, CatalogAttributeDefinition.attribute_name)
    )
    return list(db.execute(stmt).all())


def list_products(
    db: Session,
    company_id: str,
    catalog_id: int | None = None,
) -> list[tuple[Product, Catalog]]:
    stmt = (
        select(Product, Catalog)
        .join(CatalogProduct, CatalogProduct.product_id == Product.id)
        .join(Catalog, Catalog.id == CatalogProduct.catalog_id)
        .where(Product.company_tva_intra_com == company_id)
    )
    if catalog_id is not None:
        stmt = stmt.where(CatalogProduct.catalog_id == catalog_id)
    stmt = stmt.order_by(Product.updated_at.desc())
    return list(db.execute(stmt).all())


def get_product(db: Session, company_id: str, product_id: int) -> Product | None:
    return db.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.company_tva_intra_com == company_id,
        )
    )


def get_product_by_admin_sku(db: Session, admin_sku: str) -> Product | None:
    return db.scalar(select(Product).where(Product.admin_sku == admin_sku.strip()))


def _assign_admin_sku(product: Product) -> None:
    product.admin_sku = f"ADM-{product.id:08d}"


def _resolve_catalog_ids(data: ProductWrite) -> list[int]:
    ids = [data.primary_catalog_id, *data.additional_catalog_ids]
    return list(dict.fromkeys(ids))


def create_product(db: Session, company_id: str, data: ProductWrite) -> Product:
    catalog_ids = _resolve_catalog_ids(data)
    product = Product(
        admin_sku="PENDING",
        company_tva_intra_com=company_id,
        client_sku=data.client_sku.strip(),
        product_name=data.product_name.strip(),
        is_active=data.is_active,
    )
    db.add(product)
    db.flush()
    _assign_admin_sku(product)
    sync_catalog_products(db, product.id, catalog_ids)
    sync_mandatory_attributes(db, product.id, data.mandatory_attributes)
    ensure_catalog_links(
        db, data.primary_catalog_id, [c for c in catalog_ids if c != data.primary_catalog_id]
    )
    product_price_repo.append_price(
        db,
        product_id=product.id,
        price=data.price,
        currency=data.currency,
    )
    db.flush()
    return product


def update_product(db: Session, product: Product, data: ProductWrite) -> Product:
    catalog_ids = _resolve_catalog_ids(data)
    product.client_sku = data.client_sku.strip()
    product.product_name = data.product_name.strip()
    product.is_active = data.is_active
    product.updated_at = datetime.utcnow()

    sync_catalog_products(db, product.id, catalog_ids)
    sync_mandatory_attributes(db, product.id, data.mandatory_attributes)
    ensure_catalog_links(
        db, data.primary_catalog_id, [c for c in catalog_ids if c != data.primary_catalog_id]
    )

    latest = product_price_repo.get_latest_price(db, product.id)
    new_price = Decimal(str(data.price))
    new_currency = data.currency.upper()[:3]
    if latest is None or latest.price != new_price or latest.currency != new_currency:
        product_price_repo.append_price(
            db,
            product_id=product.id,
            price=new_price,
            currency=new_currency,
        )
    db.flush()
    return product


def list_product_attributes(db: Session, product_id: int) -> list[ProductAttribut]:
    stmt = select(ProductAttribut).where(ProductAttribut.product_id == product_id)
    return list(db.scalars(stmt).all())


def create_product_attribute(
    db: Session, product_id: int, data: ProductAttributWrite
) -> ProductAttribut:
    attr = ProductAttribut(
        product_id=product_id,
        name=data.name.strip(),
        value=data.value,
    )
    db.add(attr)
    db.flush()
    return attr


def delete_product_attribute(db: Session, attr_id: int, product_id: int) -> bool:
    stmt = delete(ProductAttribut).where(
        ProductAttribut.id == attr_id,
        ProductAttribut.product_id == product_id,
    )
    result = db.execute(stmt)
    return result.rowcount > 0


def update_product_attribute(
    db: Session, attr_id: int, product_id: int, data: ProductAttributWrite
) -> ProductAttribut | None:
    attr = db.scalar(
        select(ProductAttribut).where(
            ProductAttribut.id == attr_id,
            ProductAttribut.product_id == product_id,
        )
    )
    if attr is None:
        return None
    attr.name = data.name.strip()
    attr.value = data.value
    attr.updated_at = datetime.utcnow()
    db.flush()
    return attr
