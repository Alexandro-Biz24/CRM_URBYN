from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    Catalog,
    Company,
    CompanyUser,
    Product,
    ProductAttribut,
    Role,
    User,
)
from app.repositories import product_price_repo
from app.schemas.supplier_portal import (
    CatalogUpdateBody,
    CatalogWrite,
    ProductAttributWrite,
    ProductWrite,
)


def get_user(db: Session, user_id: int, email: str) -> User | None:
    normalized = email.strip().lower()
    from sqlalchemy.orm import joinedload

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
        .where(
            (Catalog.parent_id == Catalog.id) | (Catalog.parent_id.is_(None))
        )
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


def list_products(
    db: Session,
    company_id: str,
    catalog_ref: int | None = None,
) -> list[tuple[Product, Catalog]]:
    stmt = (
        select(Product, Catalog)
        .join(Catalog, Catalog.id == Product.catalog_ref)
        .where(Product.company_tva_intra_com == company_id)
    )
    if catalog_ref is not None:
        stmt = stmt.where(Product.catalog_ref == catalog_ref)
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
    return db.scalar(
        select(Product).where(Product.admin_sku == admin_sku.strip())
    )


def _assign_admin_sku(product: Product) -> None:
    product.admin_sku = f"ADM-{product.id:08d}"


def create_product(db: Session, company_id: str, data: ProductWrite) -> Product:
    product = Product(
        admin_sku="PENDING",
        catalog_ref=data.catalog_ref,
        company_tva_intra_com=company_id,
        client_sku=data.client_sku.strip(),
        product_type=data.product_type.strip(),
        quantity=data.quantity,
        is_active=data.is_active,
        teinte=data.teinte,
        type_de_produit=data.type_de_produit,
        gamme=data.gamme,
        duree_garantie=data.duree_garantie,
        conditions_garantie=data.conditions_garantie,
        piece_ouvrage_destination=data.piece_ouvrage_destination,
        traitement_bois_classification=data.traitement_bois_classification,
        produit_nuance=data.produit_nuance,
        description_profil=data.description_profil,
        couleur_traitement_autoclave=data.couleur_traitement_autoclave,
        code_douane_sh8=data.code_douane_sh8,
        type_bois=data.type_bois,
        essence_bois=data.essence_bois,
        longueur=Decimal(str(data.longueur)) if data.longueur is not None else None,
        hauteur=Decimal(str(data.hauteur)) if data.hauteur is not None else None,
        largeur=Decimal(str(data.largeur)) if data.largeur is not None else None,
        volume=Decimal(str(data.volume)) if data.volume is not None else None,
        poids_net=Decimal(str(data.poids_net)) if data.poids_net is not None else None,
    )
    db.add(product)
    db.flush()
    _assign_admin_sku(product)
    product_price_repo.append_price(
        db,
        product_id=product.id,
        price=data.price,
        currency=data.currency,
    )
    db.flush()
    return product


def update_product(db: Session, product: Product, data: ProductWrite) -> Product:
    product.catalog_ref = data.catalog_ref
    product.client_sku = data.client_sku.strip()
    product.product_type = data.product_type.strip()
    product.quantity = data.quantity
    product.is_active = data.is_active
    product.teinte = data.teinte
    product.type_de_produit = data.type_de_produit
    product.gamme = data.gamme
    product.duree_garantie = data.duree_garantie
    product.conditions_garantie = data.conditions_garantie
    product.piece_ouvrage_destination = data.piece_ouvrage_destination
    product.traitement_bois_classification = data.traitement_bois_classification
    product.produit_nuance = data.produit_nuance
    product.description_profil = data.description_profil
    product.couleur_traitement_autoclave = data.couleur_traitement_autoclave
    product.code_douane_sh8 = data.code_douane_sh8
    product.type_bois = data.type_bois
    product.essence_bois = data.essence_bois
    product.longueur = Decimal(str(data.longueur)) if data.longueur is not None else None
    product.hauteur = Decimal(str(data.hauteur)) if data.hauteur is not None else None
    product.largeur = Decimal(str(data.largeur)) if data.largeur is not None else None
    product.volume = Decimal(str(data.volume)) if data.volume is not None else None
    product.poids_net = Decimal(str(data.poids_net)) if data.poids_net is not None else None
    product.updated_at = datetime.utcnow()

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
