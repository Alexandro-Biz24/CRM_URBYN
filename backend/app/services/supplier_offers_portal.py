"""Offres du fournisseur connecté : lecture, recherche catalogue, enregistrement."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models import Address, AddressCatalog, Catalog, CatalogProduct, Product
from app.repositories import supplier_offers_repo as offers_repo
from app.repositories import supplier_portal_repo as portal_repo
from app.schemas.supplier_portal import (
    PortalSession,
    SupplierCatalogAddressWrite,
    SupplierCatalogProductHit,
    SupplierCatalogSearchGroup,
    SupplierOfferGroup,
    SupplierOfferGroupsResponse,
    SupplierOfferOut,
    SupplierOfferWrite,
    SupplierSectionSave,
)
from app.services.supplier_portal import PortalError, _resolve_context


def _catalog_index(db: Session) -> dict[int, Catalog]:
    return {catalog.id: catalog for catalog in db.scalars(select(Catalog)).all()}


def _catalog_path(index: dict[int, Catalog], catalog_id: int) -> str:
    parts: list[str] = []
    seen: set[int] = set()
    current: int | None = catalog_id
    while current is not None and current not in seen:
        seen.add(current)
        catalog = index.get(current)
        if catalog is None:
            break
        if catalog.name and catalog.name.strip():
            parts.append(catalog.name.strip())
        parent = catalog.parent_id
        if parent is None or parent == current:
            break
        current = parent
    parts.reverse()
    return " / ".join(parts) if parts else "Catalogue"


def _product_catalogs(db: Session, product_id: int) -> list[tuple[int, str]]:
    index = _catalog_index(db)
    found = [
        (catalog_id, _catalog_path(index, catalog_id))
        for catalog_id in portal_repo.get_product_catalog_ids(db, product_id)
        if catalog_id in index
    ]
    found.sort(key=lambda item: item[1].casefold())
    return found


def _catalog_label(db: Session, product_id: int) -> str:
    paths = [label for _, label in _product_catalogs(db, product_id)]
    return " · ".join(paths) if paths else "Sans catalogue"


def _address_by_catalog(db: Session, company_tva: str) -> dict[int, int]:
    rows = db.execute(
        select(AddressCatalog.catalog_id, Address.id)
        .join(Address, Address.id == AddressCatalog.address_id)
        .where(Address.company_tva_intra_com == company_tva)
    ).all()
    return {catalog_id: address_id for catalog_id, address_id in rows}


def _offer_out(db: Session, product: Product, price: Decimal, delay: int, currency: str) -> SupplierOfferOut:
    return SupplierOfferOut(
        product_id=product.id,
        product_name=product.product_name,
        client_sku=product.client_sku,
        catalog_label=_catalog_label(db, product.id),
        price=float(price),
        currency=currency,
        delai_jours=delay,
    )


def list_my_offers(db: Session, session: PortalSession) -> SupplierOfferGroupsResponse:
    ctx = _resolve_context(db, session)
    address_of = _address_by_catalog(db, ctx.company_id)
    index = _catalog_index(db)
    offers = offers_repo.latest_offers_for_company(db, ctx.company_id)
    product_ids = [offer.product_id for offer in offers]
    links: dict[int, list[int]] = {}
    if product_ids:
        for product_id, catalog_id in db.execute(
            select(CatalogProduct.product_id, CatalogProduct.catalog_id).where(
                CatalogProduct.product_id.in_(product_ids)
            )
        ).all():
            links.setdefault(product_id, []).append(catalog_id)
    products = {
        product.id: product
        for product in db.scalars(select(Product).where(Product.id.in_(product_ids))).all()
    } if product_ids else {}
    grouped: dict[tuple[int, ...], list[SupplierOfferOut]] = {}
    catalogs_of: dict[tuple[int, ...], list[tuple[int, str]]] = {}
    for offer in offers:
        product = products.get(offer.product_id)
        if product is None:
            continue
        catalogs = sorted(
            (
                (catalog_id, _catalog_path(index, catalog_id))
                for catalog_id in links.get(product.id, [])
                if catalog_id in index
            ),
            key=lambda item: item[1].casefold(),
        )
        key = tuple(catalog_id for catalog_id, _label in catalogs)
        catalogs_of[key] = catalogs
        paths = [label for _cid, label in catalogs]
        grouped.setdefault(key, []).append(
            SupplierOfferOut(
                product_id=product.id,
                product_name=product.product_name,
                client_sku=product.client_sku,
                catalog_label=" · ".join(paths) if paths else "Sans catalogue",
                price=float(offer.price),
                currency=offer.currency,
                delai_jours=int(offer.delai_jours),
            )
        )
    groups: list[SupplierOfferGroup] = []
    for key, rows in grouped.items():
        catalogs = catalogs_of.get(key, [])
        paths = [label for _cid, label in catalogs]
        linked = {address_of.get(catalog_id) for catalog_id, _label in catalogs}
        same = next(iter(linked)) if len(linked) == 1 else None
        groups.append(
            SupplierOfferGroup(
                catalog_label=" · ".join(paths) if paths else "Sans catalogue",
                catalog_ids=[catalog_id for catalog_id, _label in catalogs],
                catalog_paths=paths,
                address_id=same if isinstance(same, int) else None,
                offers=rows,
            )
        )
    groups.sort(key=lambda group: group.catalog_label.casefold())
    return SupplierOfferGroupsResponse(groups=groups)


def _company_address(db: Session, company_tva: str, address_id: int) -> Address:
    address = db.scalar(
        select(Address).where(
            Address.id == address_id,
            Address.company_tva_intra_com == company_tva,
        )
    )
    if address is None:
        raise PortalError("not_found", "Adresse introuvable.")
    if not (address.label or "").strip():
        raise PortalError("label_required", "Cette adresse n'a pas de libellé.")
    return address


def _link_catalogs(db: Session, company_tva: str, address: Address, catalog_ids: list[int]) -> None:
    ids = sorted({int(cid) for cid in catalog_ids if cid > 0})
    if not ids:
        return
    company_address_ids = list(
        db.scalars(select(Address.id).where(Address.company_tva_intra_com == company_tva)).all()
    )
    if company_address_ids:
        db.execute(
            delete(AddressCatalog).where(
                AddressCatalog.address_id.in_(company_address_ids),
                AddressCatalog.catalog_id.in_(ids),
            )
        )
    for catalog_id in ids:
        db.add(AddressCatalog(address_id=address.id, catalog_id=catalog_id))
    db.flush()


def assign_catalogs_address(db: Session, data: SupplierCatalogAddressWrite) -> None:
    """Lie une adresse du fournisseur à tous les catalogues d'un même produit."""
    ctx = _resolve_context(db, data.session)
    address = _company_address(db, ctx.company_id, data.address_id)
    _link_catalogs(db, ctx.company_id, address, data.catalog_ids)
    db.commit()


def save_section(db: Session, data: SupplierSectionSave) -> SupplierOfferGroupsResponse:
    """Prix, délais et adresses de la section, en une seule écriture."""
    ctx = _resolve_context(db, data.session)
    for item in data.addresses:
        address = _company_address(db, ctx.company_id, item.address_id)
        _link_catalogs(db, ctx.company_id, address, item.catalog_ids)
    for item in data.offers:
        product = db.get(Product, item.product_id)
        if product is None or not db.scalar(
            select(CatalogProduct.catalog_id)
            .where(CatalogProduct.product_id == product.id)
            .limit(1)
        ):
            raise PortalError("not_found", "Ce produit n'est pas dans le catalogue.")
        current = offers_repo.latest_offer(db, ctx.company_id, product.id)
        marge = Decimal(str(current.urbyn_marge)) if current is not None else Decimal("1")
        offers_repo.append_offer(
            db,
            company_tva=ctx.company_id,
            product_id=product.id,
            price=Decimal(f"{item.price:.2f}"),
            urbyn_marge=marge,
            delai_jours=item.delai_jours,
            stock=0 if current is None else int(current.stock),
            source="supplier_ui",
            currency=current.currency if current is not None else "EUR",
        )
    db.commit()
    return list_my_offers(db, data.session)


def _pick(db: Session, company_tva: str, product: Product) -> SupplierCatalogProductHit:
    current = offers_repo.latest_offer(db, company_tva, product.id)
    return SupplierCatalogProductHit(
        product_id=product.id,
        product_name=product.product_name,
        client_sku=product.client_sku,
        already_offered=current is not None,
    )


def products_in_catalog(
    db: Session, session: PortalSession, catalog_id: int
) -> list[SupplierCatalogProductHit]:
    ctx = _resolve_context(db, session)
    if portal_repo.get_catalog(db, catalog_id) is None:
        raise PortalError("not_found", "Catalogue introuvable.")
    products = db.scalars(
        select(Product)
        .join(CatalogProduct, CatalogProduct.product_id == Product.id)
        .where(CatalogProduct.catalog_id == catalog_id)
        .order_by(Product.product_name)
    ).all()
    return [_pick(db, ctx.company_id, product) for product in products]


def search_catalog_products(
    db: Session, session: PortalSession, query: str
) -> list[SupplierCatalogSearchGroup]:
    ctx = _resolve_context(db, session)
    text = " ".join(query.split())
    if len(text) < 2:
        return []
    like = f"%{text}%"
    products = db.scalars(
        select(Product)
        .join(CatalogProduct, CatalogProduct.product_id == Product.id)
        .where(or_(Product.product_name.ilike(like), Product.client_sku.ilike(like)))
        .order_by(Product.product_name)
        .distinct()
        .limit(40)
    ).all()
    groups: dict[int, SupplierCatalogSearchGroup] = {}
    for product in products:
        pick = _pick(db, ctx.company_id, product)
        for catalog_id in portal_repo.get_product_catalog_ids(db, product.id):
            group = groups.get(catalog_id)
            if group is None:
                catalog = portal_repo.get_catalog(db, catalog_id)
                if catalog is None:
                    continue
                path = portal_repo.get_breadcrumb(db, catalog)
                group = SupplierCatalogSearchGroup(
                    catalog_id=catalog_id,
                    catalog_label=" / ".join(path) if path else (catalog.name or "Catalogue"),
                    products=[],
                )
                groups[catalog_id] = group
            group.products.append(pick)
    return sorted(groups.values(), key=lambda group: group.catalog_label.casefold())


def withdraw_offer(db: Session, session: PortalSession, product_id: int) -> SupplierOfferGroupsResponse:
    """Le fournisseur n'est plus référencé sur ce produit. Le produit du catalogue reste."""
    ctx = _resolve_context(db, session)
    if offers_repo.latest_offer(db, ctx.company_id, product_id) is None:
        raise PortalError("not_found", "Vous ne proposez pas ce produit.")
    offers_repo.delete_offers_for_product(db, ctx.company_id, product_id)
    db.commit()
    return list_my_offers(db, session)


def save_offer(db: Session, data: SupplierOfferWrite) -> SupplierOfferOut:
    ctx = _resolve_context(db, data.session)
    product = db.get(Product, data.product_id)
    if product is None or not db.scalar(
        select(CatalogProduct.catalog_id).where(CatalogProduct.product_id == product.id).limit(1)
    ):
        raise PortalError("not_found", "Ce produit n'est pas dans le catalogue.")
    current = offers_repo.latest_offer(db, ctx.company_id, product.id)
    marge = Decimal(str(current.urbyn_marge)) if current is not None else Decimal("1")
    price = Decimal(f"{data.price:.2f}")
    offers_repo.append_offer(
        db,
        company_tva=ctx.company_id,
        product_id=product.id,
        price=price,
        urbyn_marge=marge,
        delai_jours=data.delai_jours,
        stock=0,
        source="supplier_ui",
    )
    db.commit()
    return _offer_out(db, product, price, data.delai_jours, "EUR")
