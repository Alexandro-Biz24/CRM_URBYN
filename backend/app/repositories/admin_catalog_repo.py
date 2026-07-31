from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models import (
    Catalog,
    CatalogAttributeDefinition,
    CatalogProduct,
    Company,
    Product,
    ProductAttribut,
    ProductMandatoryAttributeValue,
    ProductOrder,
    ProductPriceHistory,
)
from app.schemas.admin import AdminCatalogAttributeIn, AdminCatalogUpdate, AdminCatalogWrite


def _is_root(catalog: Catalog) -> bool:
    return catalog.parent_id is None or catalog.parent_id == catalog.id


def count_children(db: Session, catalog_id: int) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Catalog)
            .where(Catalog.parent_id == catalog_id, Catalog.id != catalog_id)
        )
        or 0
    )


def count_products(db: Session, catalog_id: int) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(CatalogProduct)
            .where(CatalogProduct.catalog_id == catalog_id)
        )
        or 0
    )


def list_all_catalogs(db: Session) -> list[Catalog]:
    stmt = select(Catalog).order_by(Catalog.name)
    return list(db.scalars(stmt).all())


def get_catalog(db: Session, catalog_id: int) -> Catalog | None:
    return db.get(Catalog, catalog_id)


def get_product(db: Session, product_id: int) -> Product | None:
    return db.get(Product, product_id)


def list_catalog_products(
    db: Session, catalog_id: int
) -> list[tuple[Product, Company]]:
    stmt = (
        select(Product, Company)
        .join(CatalogProduct, CatalogProduct.product_id == Product.id)
        .join(Company, Company.tva_intra_com == Product.company_tva_intra_com)
        .where(CatalogProduct.catalog_id == catalog_id)
        .order_by(Product.product_name)
    )
    return list(db.execute(stmt).all())


def list_product_catalog_names(db: Session, product_id: int) -> list[str]:
    stmt = (
        select(Catalog.name)
        .join(CatalogProduct, CatalogProduct.catalog_id == Catalog.id)
        .where(CatalogProduct.product_id == product_id)
        .order_by(Catalog.name)
    )
    return [n for n in db.scalars(stmt).all() if n]


def list_catalog_product_ids(db: Session, catalog_id: int) -> list[int]:
    return list(
        db.scalars(
            select(CatalogProduct.product_id).where(CatalogProduct.catalog_id == catalog_id)
        ).all()
    )


def list_attribute_definitions(db: Session, catalog_id: int) -> list[CatalogAttributeDefinition]:
    stmt = (
        select(CatalogAttributeDefinition)
        .where(CatalogAttributeDefinition.catalog_id == catalog_id)
        .order_by(CatalogAttributeDefinition.attribute_name)
    )
    return list(db.scalars(stmt).all())


def _ensure_product_values_for_definition(
    db: Session,
    catalog_id: int,
    definition: CatalogAttributeDefinition,
    *,
    fill_missing_with: str,
) -> None:
    """Garantit une ligne de valeur pour chaque produit du catalogue (idempotent)."""
    product_ids = list_catalog_product_ids(db, catalog_id)
    if not product_ids:
        return
    existing_product_ids = set(
        db.scalars(
            select(ProductMandatoryAttributeValue.product_id).where(
                ProductMandatoryAttributeValue.catalog_attribute_definition_id
                == definition.id,
                ProductMandatoryAttributeValue.product_id.in_(product_ids),
            )
        ).all()
    )
    now = datetime.utcnow()
    for product_id in product_ids:
        if product_id in existing_product_ids:
            continue
        db.add(
            ProductMandatoryAttributeValue(
                product_id=product_id,
                catalog_attribute_definition_id=definition.id,
                value=fill_missing_with,
                created_at=now,
                updated_at=now,
            )
        )


def sync_attribute_definitions(
    db: Session,
    catalog_id: int,
    attributes: list[AdminCatalogAttributeIn],
) -> None:
    """
    Synchronise le schéma d'attributs obligatoires du catalogue :
    - suppression d'une définition → CASCADE des valeurs produit ;
    - ajout d'une définition → backfill de tous les produits avec default_value ;
    - définition conservée → MAJ default_value + backfill des produits manquants.
    """
    cleaned: list[AdminCatalogAttributeIn] = []
    seen: set[str] = set()
    for attr in attributes:
        name = attr.attribute_name.strip()
        default = attr.default_value.strip()
        if not name or not default:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(
            AdminCatalogAttributeIn(attribute_name=name, default_value=default)
        )

    existing = list_attribute_definitions(db, catalog_id)
    existing_by_name = {a.attribute_name.lower(): a for a in existing}
    target_lower = {a.attribute_name.lower() for a in cleaned}

    for attr in existing:
        if attr.attribute_name.lower() not in target_lower:
            db.delete(attr)

    db.flush()

    for item in cleaned:
        key = item.attribute_name.lower()
        current = existing_by_name.get(key)
        if current is None:
            current = CatalogAttributeDefinition(
                catalog_id=catalog_id,
                attribute_name=item.attribute_name,
                default_value=item.default_value,
            )
            db.add(current)
            db.flush()
            _ensure_product_values_for_definition(
                db,
                catalog_id,
                current,
                fill_missing_with=item.default_value,
            )
        else:
            current.default_value = item.default_value
            current.updated_at = datetime.utcnow()
            _ensure_product_values_for_definition(
                db,
                catalog_id,
                current,
                fill_missing_with=item.default_value,
            )

    db.flush()


def resolve_catalog_attributes(
    data: AdminCatalogWrite | AdminCatalogUpdate,
) -> list[AdminCatalogAttributeIn]:
    if data.attributes:
        return list(data.attributes)
    # Legacy: noms seuls → pas de backfill fiable (défaut vide interdit)
    return [
        AdminCatalogAttributeIn(attribute_name=n.strip(), default_value="—")
        for n in data.attribute_names
        if n.strip()
    ]


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


def create_catalog(db: Session, data: AdminCatalogWrite) -> Catalog:
    parent_id = data.parent_id
    if parent_id is not None:
        parent = get_catalog(db, parent_id)
        if parent is None:
            raise ValueError("parent_not_found")
    catalog = Catalog(
        parent_id=parent_id,
        name=data.name.strip(),
        description=data.description.strip(),
        is_active=data.is_active,
    )
    db.add(catalog)
    db.flush()
    if parent_id is None:
        catalog.parent_id = catalog.id
        db.flush()
    sync_attribute_definitions(db, catalog.id, resolve_catalog_attributes(data))
    return catalog


def update_catalog(db: Session, catalog: Catalog, data: AdminCatalogUpdate) -> Catalog:
    catalog.name = data.name.strip()
    catalog.description = data.description.strip()
    catalog.is_active = data.is_active
    catalog.updated_at = datetime.utcnow()
    sync_attribute_definitions(db, catalog.id, resolve_catalog_attributes(data))
    db.flush()
    return catalog


def delete_catalog(db: Session, catalog_id: int) -> None:
    if count_children(db, catalog_id) > 0:
        raise ValueError("has_children")

    order_lines = int(
        db.scalar(
            select(func.count())
            .select_from(ProductOrder)
            .where(ProductOrder.catalog_id == catalog_id)
        )
        or 0
    )
    if order_lines > 0:
        raise ValueError("has_orders")

    product_ids = list(
        db.scalars(
            select(CatalogProduct.product_id).where(CatalogProduct.catalog_id == catalog_id)
        ).all()
    )
    if product_ids:
        db.execute(
            update(ProductOrder)
            .where(ProductOrder.product_id.in_(product_ids))
            .values(product_id=None)
        )
        db.execute(
            delete(ProductAttribut).where(ProductAttribut.product_id.in_(product_ids))
        )
        db.execute(
            delete(ProductPriceHistory).where(
                ProductPriceHistory.product_id.in_(product_ids)
            )
        )
        db.execute(delete(Product).where(Product.id.in_(product_ids)))

    db.execute(delete(Catalog).where(Catalog.id == catalog_id))
    db.flush()
