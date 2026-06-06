from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories import product_price_repo
from app.repositories import supplier_portal_repo as repo
from app.schemas.supplier_portal import (
    CatalogOut,
    CatalogUpdateBody,
    CatalogWrite,
    PortalContext,
    PortalSession,
    ProductAttributOut,
    ProductAttributUpdateBody,
    ProductAttributWrite,
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


def _catalog_out(c) -> CatalogOut:
    return CatalogOut(
        id=c.id,
        name=c.name,
        description=c.description,
        is_active=c.is_active,
        parent_id=c.parent_id,
    )


def _product_out(db: Session, p) -> ProductOut:
    latest = product_price_repo.get_latest_price(db, p.id)
    price = float(latest.price) if latest else 0.0
    currency = latest.currency if latest else "EUR"
    return ProductOut(
        id=p.id,
        admin_sku=p.admin_sku,
        catalog_ref=p.catalog_ref,
        client_sku=p.client_sku,
        product_type=p.product_type,
        price=price,
        currency=currency,
        quantity=p.quantity,
        is_active=p.is_active,
        teinte=p.teinte,
        type_de_produit=p.type_de_produit,
        gamme=p.gamme,
        duree_garantie=p.duree_garantie,
        conditions_garantie=p.conditions_garantie,
        piece_ouvrage_destination=p.piece_ouvrage_destination,
        traitement_bois_classification=p.traitement_bois_classification,
        produit_nuance=p.produit_nuance,
        description_profil=p.description_profil,
        couleur_traitement_autoclave=p.couleur_traitement_autoclave,
        code_douane_sh8=p.code_douane_sh8,
        type_bois=p.type_bois,
        essence_bois=p.essence_bois,
        longueur=float(p.longueur) if p.longueur is not None else None,
        hauteur=float(p.hauteur) if p.hauteur is not None else None,
        largeur=float(p.largeur) if p.largeur is not None else None,
        volume=float(p.volume) if p.volume is not None else None,
        poids_net=float(p.poids_net) if p.poids_net is not None else None,
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
    return [_catalog_out(c) for c in repo.search_catalogs(db, query, limit)]


def get_catalog(db: Session, session: PortalSession, catalog_id: int) -> CatalogOut:
    _resolve_context(db, session)
    c = repo.get_catalog(db, catalog_id)
    if c is None:
        raise PortalError("not_found", "Catalogue introuvable.")
    return _catalog_out(c)


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


def list_products(
    db: Session,
    session: PortalSession,
    catalog_ref: int | None = None,
) -> list[ProductListEntry]:
    ctx = _resolve_context(db, session)
    rows = repo.list_products(db, ctx.company_id, catalog_ref)
    result: list[ProductListEntry] = []
    for p, cat in rows:
        latest = product_price_repo.get_latest_price(db, p.id)
        result.append(
            ProductListEntry(
                product_id=p.id,
                admin_sku=p.admin_sku,
                client_sku=p.client_sku,
                catalog_ref=p.catalog_ref,
                catalog_name=cat.name,
                price=float(latest.price) if latest else 0.0,
                currency=latest.currency if latest else "EUR",
                quantity=p.quantity,
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
    if repo.get_catalog(db, data.catalog_ref) is None:
        raise PortalError("not_found", "Catalogue introuvable.")
    p = repo.create_product(db, ctx.company_id, data)
    db.commit()
    db.refresh(p)
    return _product_out(db, p)


def update_product(
    db: Session, product_id: int, data: ProductWrite
) -> ProductOut:
    ctx = _resolve_context(db, data.session)
    p = repo.get_product(db, ctx.company_id, product_id)
    if p is None:
        raise PortalError("not_found", "Produit introuvable.")
    if data.catalog_ref != p.catalog_ref:
        raise PortalError(
            "catalog_mismatch",
            "Le catalogue du produit ne peut pas être modifié.",
        )
    if repo.get_catalog(db, data.catalog_ref) is None:
        raise PortalError("not_found", "Catalogue introuvable.")
    p = repo.update_product(db, p, data)
    db.commit()
    db.refresh(p)
    return _product_out(db, p)


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
