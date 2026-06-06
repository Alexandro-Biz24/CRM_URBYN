from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models import Catalog, Product, ProductAttribut, ProductOrder, ProductPriceHistory
from app.schemas.admin import AdminCatalogUpdate, AdminCatalogWrite


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
            select(func.count()).select_from(Product).where(Product.catalog_ref == catalog_id)
        )
        or 0
    )


def list_all_catalogs(db: Session) -> list[Catalog]:
    stmt = select(Catalog).order_by(Catalog.name)
    return list(db.scalars(stmt).all())


def get_catalog(db: Session, catalog_id: int) -> Catalog | None:
    return db.get(Catalog, catalog_id)


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
    return catalog


def update_catalog(db: Session, catalog: Catalog, data: AdminCatalogUpdate) -> Catalog:
    catalog.name = data.name.strip()
    catalog.description = data.description.strip()
    catalog.is_active = data.is_active
    catalog.updated_at = datetime.utcnow()
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
        db.scalars(select(Product.id).where(Product.catalog_ref == catalog_id)).all()
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
