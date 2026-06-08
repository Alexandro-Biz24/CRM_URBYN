from __future__ import annotations

import secrets

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories import admin_catalog_repo as repo
from app.repositories import product_price_repo
from app.repositories import supplier_portal_repo as portal_repo
from app.schemas.admin import (
    AdminAttributeDefinitionOut,
    AdminCatalogDetail,
    AdminCatalogNode,
    AdminCatalogProductEntry,
    AdminCatalogTreeResponse,
    AdminCatalogUpdate,
    AdminCatalogWrite,
    AdminLoginResponse,
    AdminProductAttributeOut,
    AdminProductDetail,
)


class AdminError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def login(login: str, password: str) -> AdminLoginResponse:
    if not settings.admin_configured:
        raise AdminError(
            "admin_not_configured",
            "Identifiants admin non configurés (ADMIN_ID / ADMIN_PWD).",
        )
    ok_login = secrets.compare_digest(login.strip(), settings.admin_id)
    ok_pwd = secrets.compare_digest(password, settings.admin_pwd)
    if not (ok_login and ok_pwd):
        raise AdminError("invalid_credentials", "Identifiant ou mot de passe incorrect.")
    from app.core.admin_auth import create_admin_token

    token, exp = create_admin_token()
    return AdminLoginResponse(token=token, expires_at=exp)


def _build_tree(
    db: Session,
    catalogs: list,
    parent_id: int | None,
) -> list[AdminCatalogNode]:
    nodes: list[AdminCatalogNode] = []
    for c in catalogs:
        is_root = c.parent_id is None or c.parent_id == c.id
        if parent_id is None:
            if not is_root:
                continue
        elif not (c.parent_id == parent_id and c.id != parent_id):
            continue
        nodes.append(
            AdminCatalogNode(
                id=c.id,
                name=c.name,
                description=c.description,
                is_active=c.is_active,
                parent_id=c.parent_id,
                child_count=repo.count_children(db, c.id),
                product_count=repo.count_products(db, c.id),
                children=_build_tree(db, catalogs, c.id),
            )
        )
    nodes.sort(key=lambda n: (n.name or "").lower())
    return nodes


def get_catalog_tree(db: Session) -> AdminCatalogTreeResponse:
    catalogs = repo.list_all_catalogs(db)
    roots = _build_tree(db, catalogs, None)
    return AdminCatalogTreeResponse(roots=roots, total=len(catalogs))


def get_catalog_detail(db: Session, catalog_id: int) -> AdminCatalogDetail:
    c = repo.get_catalog(db, catalog_id)
    if c is None:
        raise AdminError("not_found", "Catalogue introuvable.")
    attrs = repo.list_attribute_definitions(db, c.id)
    return AdminCatalogDetail(
        id=c.id,
        name=c.name,
        description=c.description,
        is_active=c.is_active,
        parent_id=c.parent_id,
        child_count=repo.count_children(db, c.id),
        product_count=repo.count_products(db, c.id),
        breadcrumb=repo.get_breadcrumb(db, c),
        attribute_definitions=[
            AdminAttributeDefinitionOut(id=a.id, attribute_name=a.attribute_name)
            for a in attrs
        ],
    )


def create_catalog(db: Session, data: AdminCatalogWrite) -> AdminCatalogDetail:
    try:
        c = repo.create_catalog(db, data)
        db.commit()
        db.refresh(c)
    except ValueError as exc:
        db.rollback()
        if str(exc) == "parent_not_found":
            raise AdminError("parent_not_found", "Catalogue parent introuvable.") from exc
        raise
    return get_catalog_detail(db, c.id)


def update_catalog(
    db: Session, catalog_id: int, data: AdminCatalogUpdate
) -> AdminCatalogDetail:
    c = repo.get_catalog(db, catalog_id)
    if c is None:
        raise AdminError("not_found", "Catalogue introuvable.")
    repo.update_catalog(db, c, data)
    db.commit()
    db.refresh(c)
    return get_catalog_detail(db, c.id)


def list_catalog_products(db: Session, catalog_id: int) -> list[AdminCatalogProductEntry]:
    c = repo.get_catalog(db, catalog_id)
    if c is None:
        raise AdminError("not_found", "Catalogue introuvable.")
    rows = repo.list_catalog_products(db, catalog_id)
    result: list[AdminCatalogProductEntry] = []
    for product, company in rows:
        latest = product_price_repo.get_latest_price(db, product.id)
        result.append(
            AdminCatalogProductEntry(
                product_id=product.id,
                admin_sku=product.admin_sku,
                product_name=product.product_name,
                company_name=company.company_name,
                price=float(latest.price) if latest else 0.0,
                currency=latest.currency if latest else "EUR",
                is_active=product.is_active,
            )
        )
    return result


def get_product_detail(db: Session, product_id: int) -> AdminProductDetail:
    product = repo.get_product(db, product_id)
    if product is None:
        raise AdminError("not_found", "Produit introuvable.")
    company = product.company
    latest = product_price_repo.get_latest_price(db, product.id)
    mandatory = [
        AdminProductAttributeOut(
            name=f"{defn.attribute_name} ({defn.catalog_id})",
            value=val.value,
        )
        for val, defn in portal_repo.list_mandatory_attribute_values(db, product.id)
    ]
    free_attrs = [
        AdminProductAttributeOut(name=a.name, value=a.value)
        for a in sorted(product.attributes, key=lambda x: x.name.lower())
    ]
    return AdminProductDetail(
        id=product.id,
        admin_sku=product.admin_sku,
        client_sku=product.client_sku,
        product_name=product.product_name,
        company_name=company.company_name if company else "—",
        company_tva=product.company_tva_intra_com,
        price=float(latest.price) if latest else 0.0,
        currency=latest.currency if latest else "EUR",
        is_active=product.is_active,
        catalog_names=repo.list_product_catalog_names(db, product.id),
        mandatory_attributes=mandatory,
        free_attributes=free_attrs,
    )


def delete_catalog(db: Session, catalog_id: int) -> None:
    c = repo.get_catalog(db, catalog_id)
    if c is None:
        raise AdminError("not_found", "Catalogue introuvable.")
    try:
        repo.delete_catalog(db, catalog_id)
        db.commit()
    except ValueError as exc:
        db.rollback()
        code = str(exc)
        if code == "has_children":
            raise AdminError(
                "has_children",
                "Supprimez d'abord tous les sous-catalogues.",
            ) from exc
        if code == "has_orders":
            raise AdminError(
                "has_orders",
                "Ce catalogue est lié à des commandes et ne peut pas être supprimé.",
            ) from exc
        raise
