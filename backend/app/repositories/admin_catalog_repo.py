from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from decimal import Decimal

from app.models import (
    Catalog,
    CatalogAttributeDefinition,
    CatalogProduct,
    Company,
    Language,
    Product,
    ProductAttribut,
    ProductMandatoryAttributeValue,
    ProductOrder,
    ProductPriceHistory,
    ProductTranslation,
)
from app.repositories import product_price_repo
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
    names = data.attribute_names or []
    # Legacy: noms seuls → pas de backfill fiable (défaut vide interdit)
    return [
        AdminCatalogAttributeIn(attribute_name=n.strip(), default_value="—")
        for n in names
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
    # Ne synchronise le schéma que si le client envoie explicitement attributes / attribute_names
    if data.attributes is not None or data.attribute_names is not None:
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


# ---------------------------------------------------------------------------
# Import CSV + attributs produits d'un catalogue
# ---------------------------------------------------------------------------


def get_company(db: Session, tva_intra_com: str) -> Company | None:
    return db.get(Company, tva_intra_com.strip())


def find_company_by_name(db: Session, name: str) -> Company | None:
    """Match souple du nom société (exact, préfixe, puis premier mot significatif)."""
    cleaned = " ".join((name or "").split()).strip()
    if not cleaned:
        return None
    exact = db.scalar(
        select(Company).where(func.lower(Company.company_name) == cleaned.lower())
    )
    if exact is not None:
        return exact
    prefix = db.scalar(
        select(Company)
        .where(Company.company_name.ilike(f"{cleaned}%"))
        .order_by(func.length(Company.company_name))
        .limit(1)
    )
    if prefix is not None:
        return prefix
    # « ALKERN FRANCE - Béton… » → cherche ALKERN
    token = cleaned.split()[0]
    if len(token) >= 4:
        return db.scalar(
            select(Company)
            .where(Company.company_name.ilike(f"%{token}%"))
            .order_by(func.length(Company.company_name))
            .limit(1)
        )
    return None


_DEFAULT_URBANIZE_TVA = "FRURBANIZE00001"
_DEFAULT_URBANIZE_NAME = "Urbanize"


def ensure_urbanize_company(db: Session) -> Company:
    """Société propriétaire par défaut quand Fournisseur CSV est vide."""
    existing = find_company_by_name(db, _DEFAULT_URBANIZE_NAME)
    if existing is not None:
        return existing
    by_tva = get_company(db, _DEFAULT_URBANIZE_TVA)
    if by_tva is not None:
        return by_tva
    company = Company(
        tva_intra_com=_DEFAULT_URBANIZE_TVA,
        company_name=_DEFAULT_URBANIZE_NAME,
        email="contact@urbanize.site",
        cgv_accepted=True,
        is_verified=True,
        description="Société plateforme Urbanize (import catalogue).",
    )
    db.add(company)
    db.flush()
    return company


def find_product_by_client_sku(
    db: Session, company_tva: str, client_sku: str
) -> Product | None:
    return db.scalar(
        select(Product).where(
            Product.company_tva_intra_com == company_tva,
            Product.client_sku == client_sku.strip(),
        )
    )


def _find_root_by_name(db: Session, name: str) -> Catalog | None:
    stmt = select(Catalog).where(Catalog.name == name)
    for catalog in db.scalars(stmt).all():
        if _is_root(catalog):
            return catalog
    return None


def _find_child_by_name(db: Session, parent_id: int, name: str) -> Catalog | None:
    return db.scalar(
        select(Catalog).where(
            Catalog.parent_id == parent_id,
            Catalog.id != parent_id,
            Catalog.name == name,
        )
    )


def ensure_catalog_path(
    db: Session, segments: list[str]
) -> tuple[Catalog, set[int]]:
    """Crée / réutilise le chemin racine→feuille. Retourne (feuille, ids créés)."""
    created_ids: set[int] = set()
    parent: Catalog | None = None
    leaf: Catalog | None = None

    for index, raw_name in enumerate(segments):
        name = raw_name.strip()
        if not name:
            continue
        if index == 0:
            current = _find_root_by_name(db, name)
            if current is None:
                current = Catalog(
                    parent_id=None,
                    name=name,
                    description=f"Catalogue importé : {name}",
                    is_active=True,
                )
                db.add(current)
                db.flush()
                current.parent_id = current.id
                db.flush()
                created_ids.add(current.id)
        else:
            assert parent is not None
            current = _find_child_by_name(db, parent.id, name)
            if current is None:
                current = Catalog(
                    parent_id=parent.id,
                    name=name,
                    description=f"Catalogue importé : {' / '.join(segments[: index + 1])}",
                    is_active=True,
                )
                db.add(current)
                db.flush()
                created_ids.add(current.id)
        parent = current
        leaf = current

    if leaf is None:
        raise ValueError("empty_catalog_path")
    return leaf, created_ids


def clear_catalog_products(db: Session, catalog_id: int) -> int:
    result = db.execute(
        delete(CatalogProduct).where(CatalogProduct.catalog_id == catalog_id)
    )
    db.flush()
    return int(result.rowcount or 0)


def create_imported_product(
    db: Session,
    *,
    company_tva: str,
    client_sku: str,
    product_name: str,
) -> Product:
    product = Product(
        admin_sku="PENDING",
        company_tva_intra_com=company_tva,
        client_sku=client_sku.strip(),
        product_name=product_name.strip(),
        is_active=True,
    )
    db.add(product)
    db.flush()
    product.admin_sku = f"ADM-{product.id:08d}"
    db.flush()
    return product


def _default_language_id(db: Session) -> int | None:
    lang = db.scalar(
        select(Language).where(Language.is_default.is_(True)).limit(1)
    )
    if lang is not None:
        return lang.id
    lang = db.scalar(select(Language).where(Language.code == "fr").limit(1))
    if lang is not None:
        return lang.id
    lang = db.scalar(select(Language).limit(1))
    return lang.id if lang else None


def upsert_product_description(db: Session, product_id: int, description: str) -> None:
    text = (description or "").strip()
    if not text:
        return
    language_id = _default_language_id(db)
    if language_id is None:
        # Pas de table languages peuplée : stocke en attribut libre
        upsert_free_attributes(db, product_id, {"Description": text})
        return
    existing = db.scalar(
        select(ProductTranslation).where(
            ProductTranslation.product_id == product_id,
            ProductTranslation.language_id == language_id,
        )
    )
    if existing is None:
        db.add(
            ProductTranslation(
                product_id=product_id,
                language_id=language_id,
                description=text,
            )
        )
    else:
        existing.description = text
        existing.updated_at = datetime.utcnow()
    db.flush()


def upsert_product_price(
    db: Session,
    *,
    product_id: int,
    price: Decimal,
    currency: str,
) -> None:
    latest = product_price_repo.get_latest_price(db, product_id)
    currency_code = currency.upper()[:3]
    if (
        latest is not None
        and latest.price == price
        and latest.currency == currency_code
    ):
        return
    product_price_repo.append_price(
        db,
        product_id=product_id,
        price=price,
        currency=currency_code,
    )


def upsert_free_attributes(
    db: Session, product_id: int, attrs: dict[str, str]
) -> None:
    if not attrs:
        return
    existing = {
        a.name.lower(): a
        for a in db.scalars(
            select(ProductAttribut).where(ProductAttribut.product_id == product_id)
        ).all()
    }
    now = datetime.utcnow()
    for name, value in attrs.items():
        key = name.lower()
        current = existing.get(key)
        if current is None:
            db.add(
                ProductAttribut(
                    product_id=product_id,
                    name=name,
                    value=value,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            current.value = value
            current.updated_at = now
    db.flush()


def link_product_to_catalog(db: Session, catalog_id: int, product_id: int) -> bool:
    exists = db.scalar(
        select(CatalogProduct.catalog_id).where(
            CatalogProduct.catalog_id == catalog_id,
            CatalogProduct.product_id == product_id,
        )
    )
    if exists is not None:
        return False
    db.add(CatalogProduct(catalog_id=catalog_id, product_id=product_id))
    db.flush()
    return True


def list_product_attribute_stats(
    db: Session, catalog_id: int
) -> list[tuple[str, int]]:
    """Noms d'attributs libres présents sur les produits du catalogue + occurrences."""
    stmt = (
        select(ProductAttribut.name, func.count(func.distinct(ProductAttribut.product_id)))
        .join(CatalogProduct, CatalogProduct.product_id == ProductAttribut.product_id)
        .where(CatalogProduct.catalog_id == catalog_id)
        .group_by(ProductAttribut.name)
        .order_by(ProductAttribut.name)
    )
    return [(name, int(count)) for name, count in db.execute(stmt).all()]


def get_attribute_definition_by_name(
    db: Session, catalog_id: int, attribute_name: str
) -> CatalogAttributeDefinition | None:
    return db.scalar(
        select(CatalogAttributeDefinition).where(
            CatalogAttributeDefinition.catalog_id == catalog_id,
            func.lower(CatalogAttributeDefinition.attribute_name)
            == attribute_name.strip().lower(),
        )
    )


def set_attribute_mandatory(
    db: Session,
    catalog_id: int,
    attribute_name: str,
    *,
    is_mandatory: bool,
) -> CatalogAttributeDefinition | None:
    """
    Active / désactive le caractère obligatoire d'un attribut présent sur les produits.
    - ON  : crée la définition + backfill des valeurs depuis product_attribut
    - OFF : supprime la définition (CASCADE des valeurs mandatory)
    """
    name = attribute_name.strip()
    if not name:
        raise ValueError("empty_attribute_name")

    existing = get_attribute_definition_by_name(db, catalog_id, name)

    if not is_mandatory:
        if existing is not None:
            db.delete(existing)
            db.flush()
        return None

    if existing is None:
        # Valeur par défaut = première valeur non vide trouvée, sinon tiret
        sample = db.scalar(
            select(ProductAttribut.value)
            .join(CatalogProduct, CatalogProduct.product_id == ProductAttribut.product_id)
            .where(
                CatalogProduct.catalog_id == catalog_id,
                func.lower(ProductAttribut.name) == name.lower(),
                ProductAttribut.value.is_not(None),
                func.btrim(ProductAttribut.value) != "",
            )
            .limit(1)
        )
        default_value = (sample or "—").strip() or "—"
        existing = CatalogAttributeDefinition(
            catalog_id=catalog_id,
            attribute_name=name,
            default_value=default_value,
        )
        db.add(existing)
        db.flush()

    product_ids = list_catalog_product_ids(db, catalog_id)
    if product_ids:
        attr_by_product = {
            row.product_id: (row.value or "").strip()
            for row in db.scalars(
                select(ProductAttribut).where(
                    ProductAttribut.product_id.in_(product_ids),
                    func.lower(ProductAttribut.name) == name.lower(),
                )
            ).all()
        }
        existing_values = {
            row.product_id: row
            for row in db.scalars(
                select(ProductMandatoryAttributeValue).where(
                    ProductMandatoryAttributeValue.catalog_attribute_definition_id
                    == existing.id,
                    ProductMandatoryAttributeValue.product_id.in_(product_ids),
                )
            ).all()
        }
        now = datetime.utcnow()
        for product_id in product_ids:
            value = attr_by_product.get(product_id) or existing.default_value
            current = existing_values.get(product_id)
            if current is None:
                db.add(
                    ProductMandatoryAttributeValue(
                        product_id=product_id,
                        catalog_attribute_definition_id=existing.id,
                        value=value,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                current.value = value
                current.updated_at = now
    db.flush()
    return existing
