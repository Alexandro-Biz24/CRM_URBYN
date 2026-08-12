from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Catalog, CatalogProduct, Company, Product
from app.repositories import product_price_repo, supplier_portal_repo as catalog_repo


def list_active_root_catalogs(db: Session) -> list[Catalog]:
    stmt = (
        select(Catalog)
        .where(
            Catalog.is_active.is_(True),
            (Catalog.parent_id == Catalog.id) | (Catalog.parent_id.is_(None)),
        )
        .order_by(Catalog.name)
    )
    return list(db.scalars(stmt).all())


def list_active_catalog_children(db: Session, parent_id: int) -> list[Catalog]:
    stmt = (
        select(Catalog)
        .where(
            Catalog.is_active.is_(True),
            Catalog.parent_id == parent_id,
            Catalog.id != parent_id,
        )
        .order_by(Catalog.name)
    )
    return list(db.scalars(stmt).all())


def has_active_children(db: Session, catalog_id: int) -> bool:
    return len(list_active_catalog_children(db, catalog_id)) > 0


def collect_leaf_catalog_ids(db: Session, catalog_id: int) -> list[int]:
    return [c.id for c in collect_leaf_catalogs(db, catalog_id)]


def collect_leaf_catalogs(db: Session, catalog_id: int) -> list[Catalog]:
    """Retourne les catalogues feuilles (sans enfants actifs) sous un nœud."""
    catalog = catalog_repo.get_catalog(db, catalog_id)
    if catalog is None or not catalog.is_active:
        return []

    children = list_active_catalog_children(db, catalog_id)
    if not children:
        return [catalog]

    leaves: list[Catalog] = []
    for child in children:
        leaves.extend(collect_leaf_catalogs(db, child.id))
    return leaves


def _normalize_catalog_name(name: str) -> str:
    """Compare les noms catalogue en ignorant casse, _ / - et espaces multiples."""
    cleaned = (name or "").strip().replace("_", " ").replace("-", " ")
    return " ".join(cleaned.split()).casefold()


def find_active_root_catalog_by_name(db: Session, name: str) -> Catalog | None:
    needle = _normalize_catalog_name(name)
    if not needle:
        return None
    stmt = (
        select(Catalog)
        .where(
            Catalog.is_active.is_(True),
            (Catalog.parent_id == Catalog.id) | (Catalog.parent_id.is_(None)),
        )
        .order_by(Catalog.id)
    )
    for catalog in db.scalars(stmt):
        if _normalize_catalog_name(catalog.name or "") == needle:
            return catalog
    return None


def list_marketplace_products_in_catalogs(
    db: Session,
    catalog_ids: list[int],
) -> list[tuple[Product, Company]]:
    if not catalog_ids:
        return []

    stmt = (
        select(Product, Company)
        .join(CatalogProduct, CatalogProduct.product_id == Product.id)
        .join(Catalog, Catalog.id == CatalogProduct.catalog_id)
        .join(Company, Company.tva_intra_com == Product.company_tva_intra_com)
        .where(
            CatalogProduct.catalog_id.in_(catalog_ids),
            Product.is_active.is_(True),
            Catalog.is_active.is_(True),
        )
        .order_by(Product.product_name, Product.id)
    )
    rows = list(db.execute(stmt).all())
    seen: set[int] = set()
    unique: list[tuple[Product, Company]] = []
    for product, company in rows:
        if product.id in seen:
            continue
        seen.add(product.id)
        unique.append((product, company))
    return unique


def search_active_products(
    db: Session,
    query: str,
    limit: int = 20,
) -> list[Product]:
    q = query.strip()
    if not q:
        return []
    pattern = f"%{q}%"
    stmt = (
        select(Product)
        .where(
            Product.is_active.is_(True),
            (Product.product_name.ilike(pattern))
            | (Product.admin_sku.ilike(pattern)),
        )
        .order_by(Product.product_name)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def search_active_catalogs(
    db: Session,
    query: str,
    limit: int = 20,
) -> list[Catalog]:
    return catalog_repo.search_catalogs(db, query, limit=limit)


def build_breadcrumb_chain(db: Session, catalog: Catalog) -> list[Catalog]:
    names_and_ids: list[Catalog] = []
    current: Catalog | None = catalog
    seen: set[int] = set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        names_and_ids.append(current)
        if current.parent_id is None or current.parent_id == current.id:
            break
        current = catalog_repo.get_catalog(db, current.parent_id)
    names_and_ids.reverse()
    return names_and_ids


def resolve_catalog_ref(db: Session, ref: str) -> list[Catalog]:
    """Résout une référence catalogue (ID numérique ou nom exact, insensible à la casse)."""
    token = ref.strip()
    if not token:
        return []
    if token.isdigit():
        catalog = catalog_repo.get_catalog(db, int(token))
        if catalog is not None and catalog.is_active:
            return [catalog]
        return []
    stmt = (
        select(Catalog)
        .where(Catalog.is_active.is_(True), Catalog.name.ilike(token))
        .order_by(Catalog.name)
    )
    return list(db.scalars(stmt).all())


def collect_leaf_ids_for_catalog_refs(db: Session, catalog_refs: list[str]) -> list[int]:
    leaf_ids: set[int] = set()
    for ref in catalog_refs:
        for catalog in resolve_catalog_ref(db, ref):
            for leaf_id in collect_leaf_catalog_ids(db, catalog.id):
                leaf_ids.add(leaf_id)
    return sorted(leaf_ids)


def get_product_catalog_links_in_catalogs(
    db: Session,
    catalog_ids: list[int],
) -> list[tuple[Product, Company, Catalog]]:
    if not catalog_ids:
        return []
    stmt = (
        select(Product, Company, Catalog)
        .join(CatalogProduct, CatalogProduct.product_id == Product.id)
        .join(Catalog, Catalog.id == CatalogProduct.catalog_id)
        .join(Company, Company.tva_intra_com == Product.company_tva_intra_com)
        .where(
            CatalogProduct.catalog_id.in_(catalog_ids),
            Product.is_active.is_(True),
            Catalog.is_active.is_(True),
        )
        .order_by(Product.product_name, Product.id)
    )
    return list(db.execute(stmt).all())

