from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories import product_price_repo
from app.repositories import supplier_portal_repo as repo
from app.schemas.supplier_portal import (
    CatalogAttributeDefinitionOut,
    CatalogOut,
    CatalogUpdateBody,
    CatalogWrite,
    MandatoryAttributeValueOut,
    PortalContext,
    PortalSession,
    ProductAttributOut,
    ProductAttributUpdateBody,
    ProductAttributWrite,
    ProductCatalogGroup,
    ProductCatalogGroupsResponse,
    ProductListEntry,
    ProductOut,
    ProductWrite,
)


class PortalError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _resolve_context(db: Session, session: PortalSession) -> PortalContext:
    user = repo.get_user(db, session.user_id, str(session.email))
    if user is None:
        raise PortalError("session_mismatch", "Session invalide.")
    if user.role is None or user.role.role_name != "Fournisseur":
        raise PortalError("role_mismatch", "Accès réservé aux fournisseurs.")
    row = repo.get_company_for_user(db, user.id)
    if row is None:
        raise PortalError("no_company", "Aucune société rattachée à ce compte.")
    company_id, company_name = row
    return PortalContext(
        user_id=user.id,
        company_id=company_id,
        company_name=company_name,
    )


def _catalog_out(c, *, breadcrumb: list[str] | None = None) -> CatalogOut:
    return CatalogOut(
        id=c.id,
        name=c.name,
        description=c.description,
        is_active=c.is_active,
        parent_id=c.parent_id,
        breadcrumb=breadcrumb or [],
    )


def _mandatory_out(rows) -> list[MandatoryAttributeValueOut]:
    return [
        MandatoryAttributeValueOut(
            definition_id=defn.id,
            catalog_id=defn.catalog_id,
            attribute_name=defn.attribute_name,
            value=val.value,
        )
        for val, defn in rows
    ]


def _product_out(db: Session, p, primary_catalog_id: int | None = None) -> ProductOut:
    latest = product_price_repo.get_latest_price(db, p.id)
    price = float(latest.price) if latest else 0.0
    currency = latest.currency if latest else "EUR"
    catalog_ids = repo.get_product_catalog_ids(db, p.id)
    primary = primary_catalog_id or (catalog_ids[0] if catalog_ids else 0)
    mandatory = _mandatory_out(repo.list_mandatory_attribute_values(db, p.id))
    linked_catalogs: list[CatalogOut] = []
    for cid in catalog_ids:
        c = repo.get_catalog(db, cid)
        if c is not None:
            linked_catalogs.append(
                _catalog_out(c, breadcrumb=repo.get_breadcrumb(db, c))
            )
    return ProductOut(
        id=p.id,
        admin_sku=p.admin_sku,
        primary_catalog_id=primary,
        catalog_ids=catalog_ids,
        linked_catalogs=linked_catalogs,
        client_sku=p.client_sku,
        product_name=p.product_name,
        price=price,
        currency=currency,
        is_active=p.is_active,
        mandatory_attributes=mandatory,
    )


def _validate_catalogs_exist(db: Session, catalog_ids: list[int]) -> None:
    for cid in catalog_ids:
        if repo.get_catalog(db, cid) is None:
            raise PortalError("not_found", f"Catalogue introuvable : {cid}.")


def _validate_mandatory_attributes(
    db: Session, catalog_ids: list[int], provided: list
) -> None:
    definitions = repo.list_attribute_definitions_for_catalogs(db, catalog_ids)
    if not definitions:
        return
    provided_map = {v.definition_id: v.value.strip() for v in provided}
    missing: list[str] = []
    for defn in definitions:
        val = provided_map.get(defn.id, "").strip()
        if not val:
            missing.append(defn.attribute_name)
    if missing:
        raise PortalError(
            "missing_mandatory_attributes",
            f"Attributs obligatoires manquants : {', '.join(missing)}.",
        )


def get_context(db: Session, session: PortalSession) -> PortalContext:
    return _resolve_context(db, session)


def list_catalogs(db: Session, session: PortalSession) -> list[CatalogOut]:
    _resolve_context(db, session)
    return [_catalog_out(c) for c in repo.list_catalogs(db)]


def list_root_catalogs(db: Session, session: PortalSession) -> list[CatalogOut]:
    _resolve_context(db, session)
    return [_catalog_out(c) for c in repo.list_root_catalogs(db)]


def list_catalog_children(
    db: Session, session: PortalSession, parent_id: int
) -> list[CatalogOut]:
    _resolve_context(db, session)
    parent = repo.get_catalog(db, parent_id)
    if parent is None:
        raise PortalError("not_found", "Catalogue introuvable.")
    return [_catalog_out(c) for c in repo.list_catalog_children(db, parent_id)]


def search_catalogs(
    db: Session, session: PortalSession, query: str, limit: int = 30
) -> list[CatalogOut]:
    _resolve_context(db, session)
    return [
        _catalog_out(c, breadcrumb=repo.get_breadcrumb(db, c))
        for c in repo.search_catalogs(db, query, limit)
    ]


def get_catalog(db: Session, session: PortalSession, catalog_id: int) -> CatalogOut:
    _resolve_context(db, session)
    c = repo.get_catalog(db, catalog_id)
    if c is None:
        raise PortalError("not_found", "Catalogue introuvable.")
    return _catalog_out(c)


def list_catalog_attribute_definitions(
    db: Session, session: PortalSession, catalog_id: int
) -> list[CatalogAttributeDefinitionOut]:
    _resolve_context(db, session)
    if repo.get_catalog(db, catalog_id) is None:
        raise PortalError("not_found", "Catalogue introuvable.")
    return [
        CatalogAttributeDefinitionOut(
            id=d.id,
            catalog_id=d.catalog_id,
            attribute_name=d.attribute_name,
            default_value=getattr(d, "default_value", None) or "",
        )
        for d in repo.list_catalog_attribute_definitions(db, catalog_id)
    ]


def create_catalog(db: Session, data: CatalogWrite) -> CatalogOut:
    _resolve_context(db, data.session)
    if data.parent_id is not None:
        parent = repo.get_catalog(db, data.parent_id)
        if parent is None:
            raise PortalError("parent_not_found", "Catalogue parent introuvable.")
    c = repo.create_catalog(db, data)
    db.commit()
    db.refresh(c)
    return _catalog_out(c)


def update_catalog(
    db: Session, catalog_id: int, data: CatalogUpdateBody
) -> CatalogOut:
    _resolve_context(db, data.session)
    c = repo.get_catalog(db, catalog_id)
    if c is None:
        raise PortalError("not_found", "Catalogue introuvable.")
    c = repo.update_catalog(db, c, data)
    db.commit()
    db.refresh(c)
    return _catalog_out(c)


def list_products_grouped(
    db: Session,
    session: PortalSession,
) -> ProductCatalogGroupsResponse:
    ctx = _resolve_context(db, session)
    rows = repo.list_products(db, ctx.company_id, None)
    groups: dict[int, ProductCatalogGroup] = {}
    seen: dict[int, set[int]] = {}
    for p, cat in rows:
        if cat.id not in groups:
            groups[cat.id] = ProductCatalogGroup(
                catalog_id=cat.id,
                catalog_name=cat.name,
                products=[],
            )
            seen[cat.id] = set()
        if p.id in seen[cat.id]:
            continue
        seen[cat.id].add(p.id)
        latest = product_price_repo.get_latest_price(db, p.id)
        catalog_ids = repo.get_product_catalog_ids(db, p.id)
        primary = catalog_ids[0] if catalog_ids else cat.id
        groups[cat.id].products.append(
            ProductListEntry(
                product_id=p.id,
                admin_sku=p.admin_sku,
                client_sku=p.client_sku,
                product_name=p.product_name,
                primary_catalog_id=primary,
                catalog_name=cat.name,
                price=float(latest.price) if latest else 0.0,
                currency=latest.currency if latest else "EUR",
                is_active=p.is_active,
            )
        )
    ordered = sorted(
        groups.values(),
        key=lambda g: (g.catalog_name or "").lower(),
    )
    return ProductCatalogGroupsResponse(groups=ordered)


def list_products(
    db: Session,
    session: PortalSession,
    catalog_id: int | None = None,
) -> list[ProductListEntry]:
    ctx = _resolve_context(db, session)
    rows = repo.list_products(db, ctx.company_id, catalog_id)
    result: list[ProductListEntry] = []
    seen: set[int] = set()
    for p, cat in rows:
        if p.id in seen:
            continue
        seen.add(p.id)
        latest = product_price_repo.get_latest_price(db, p.id)
        catalog_ids = repo.get_product_catalog_ids(db, p.id)
        primary = catalog_ids[0] if catalog_ids else cat.id
        result.append(
            ProductListEntry(
                product_id=p.id,
                admin_sku=p.admin_sku,
                client_sku=p.client_sku,
                product_name=p.product_name,
                primary_catalog_id=primary,
                catalog_name=cat.name,
                price=float(latest.price) if latest else 0.0,
                currency=latest.currency if latest else "EUR",
                is_active=p.is_active,
            )
        )
    return result


def get_product(db: Session, session: PortalSession, product_id: int) -> ProductOut:
    ctx = _resolve_context(db, session)
    p = repo.get_product(db, ctx.company_id, product_id)
    if p is None:
        raise PortalError("not_found", "Produit introuvable.")
    return _product_out(db, p)


def create_product(db: Session, data: ProductWrite) -> ProductOut:
    ctx = _resolve_context(db, data.session)
    catalog_ids = [data.primary_catalog_id, *data.additional_catalog_ids]
    catalog_ids = list(dict.fromkeys(catalog_ids))
    _validate_catalogs_exist(db, catalog_ids)
    _validate_mandatory_attributes(db, catalog_ids, data.mandatory_attributes)
    p = repo.create_product(db, ctx.company_id, data)
    db.commit()
    db.refresh(p)
    return _product_out(db, p, data.primary_catalog_id)


def update_product(
    db: Session, product_id: int, data: ProductWrite
) -> ProductOut:
    ctx = _resolve_context(db, data.session)
    p = repo.get_product(db, ctx.company_id, product_id)
    if p is None:
        raise PortalError("not_found", "Produit introuvable.")
    catalog_ids = [data.primary_catalog_id, *data.additional_catalog_ids]
    catalog_ids = list(dict.fromkeys(catalog_ids))
    _validate_catalogs_exist(db, catalog_ids)
    _validate_mandatory_attributes(db, catalog_ids, data.mandatory_attributes)
    p = repo.update_product(db, p, data)
    db.commit()
    db.refresh(p)
    return _product_out(db, p, data.primary_catalog_id)


def list_attributes(
    db: Session, session: PortalSession, product_id: int
) -> list[ProductAttributOut]:
    ctx = _resolve_context(db, session)
    p = repo.get_product(db, ctx.company_id, product_id)
    if p is None:
        raise PortalError("not_found", "Produit introuvable.")
    return [
        ProductAttributOut(id=a.id, name=a.name, value=a.value)
        for a in repo.list_product_attributes(db, product_id)
    ]


def add_attribute(
    db: Session, product_id: int, data: ProductAttributWrite
) -> ProductAttributOut:
    ctx = _resolve_context(db, data.session)
    p = repo.get_product(db, ctx.company_id, product_id)
    if p is None:
        raise PortalError("not_found", "Produit introuvable.")
    a = repo.create_product_attribute(db, product_id, data)
    db.commit()
    db.refresh(a)
    return ProductAttributOut(id=a.id, name=a.name, value=a.value)


def update_attribute(
    db: Session, product_id: int, attr_id: int, data: ProductAttributUpdateBody
) -> ProductAttributOut:
    ctx = _resolve_context(db, data.session)
    p = repo.get_product(db, ctx.company_id, product_id)
    if p is None:
        raise PortalError("not_found", "Produit introuvable.")
    a = repo.update_product_attribute(db, attr_id, product_id, data)
    if a is None:
        raise PortalError("not_found", "Attribut introuvable.")
    db.commit()
    db.refresh(a)
    return ProductAttributOut(id=a.id, name=a.name, value=a.value)


def delete_attribute(
    db: Session, session: PortalSession, product_id: int, attr_id: int
) -> None:
    ctx = _resolve_context(db, session)
    p = repo.get_product(db, ctx.company_id, product_id)
    if p is None:
        raise PortalError("not_found", "Produit introuvable.")
    if not repo.delete_product_attribute(db, attr_id, product_id):
        raise PortalError("not_found", "Attribut introuvable.")
    db.commit()
