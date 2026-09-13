from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import AddressCatalog, Catalog, CatalogProduct, Company, Product
from app.models.address import Address
from app.repositories import cart_repo
from app.repositories import client_portal_repo as buyer_repo
from app.repositories import product_price_repo, supplier_portal_repo as repo
from app.services import buyer_shipping
from app.schemas.client_portal import (
    MASSIF_ROOT_DEFAULT,
    TOTEM_ROOT_DEFAULT,
    BuyerCatalogNavItem,
    BuyerCatalogNavigation,
    BuyerProductCard,
    BuyerProductDetail,
    BuyerSearchHit,
    BuyerShippingOption,
    CartItemOut,
    CartOut,
    CartSnapshotOut,
    MassifLeafCatalogOut,
    MassifLeafCatalogsResponse,
    MassifManilleOut,
    MassifManillesResponse,
    MassifPaletteOut,
    MassifPaletteResponse,
    MassifProductOut,
    MassifProductsRequest,
    MassifProductsResponse,
    MassifWeightBandOut,
    MassifWeightBandsResponse,
    ProductAttributeOut,
    ProductWeightFilterItem,
    ProductWeightFilterRequest,
    ProductWeightFilterResponse,
    ProductDimensionsOut,
    ShippingCheckRequest,
    ShippingCheckResponse,
    ShippingQuoteRequest,
    TotemBallastOut,
    TotemBallastsResponse,
    TotemFamiliesResponse,
    TotemFamilyOut,
    TotemProductDetailOut,
    TotemProductOut,
    TotemProductsResponse,
)
from app.schemas.supplier_portal import CatalogOut, MandatoryAttributeValueOut, PortalContext, PortalSession


class ClientPortalError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _require_client_session(db: Session, session: PortalSession) -> PortalContext:
    user = repo.get_user(db, session.user_id, str(session.email))
    if user is None:
        raise ClientPortalError("session_mismatch", "Session invalide.")
    if user.role is None or user.role.role_name != "Client":
        raise ClientPortalError("role_mismatch", "Accès réservé aux clients.")
    row = repo.get_company_for_user(db, user.id)
    if row is None:
        raise ClientPortalError("no_company", "Aucune société rattachée à ce compte.")
    company_id, company_name = row
    return PortalContext(
        user_id=user.id,
        company_id=company_id,
        company_name=company_name,
    )


def get_context(db: Session, session: PortalSession) -> PortalContext:
    return _require_client_session(db, session)


def _catalog_out(db: Session, catalog: object) -> CatalogOut:
    c = catalog
    return CatalogOut(
        id=c.id,
        name=c.name,
        description=c.description,
        is_active=c.is_active,
        parent_id=c.parent_id,
        breadcrumb=repo.get_breadcrumb(db, c),
    )


def _mandatory_out(
    product_id: int,
    db: Session,
    *,
    catalog_id: int | None = None,
) -> list[MandatoryAttributeValueOut]:
    rows = []
    for val, defn in repo.list_mandatory_attribute_values(db, product_id):
        if catalog_id is not None and defn.catalog_id != catalog_id:
            continue
        rows.append(
            MandatoryAttributeValueOut(
                definition_id=defn.id,
                catalog_id=defn.catalog_id,
                attribute_name=defn.attribute_name,
                value=val.value,
            )
        )
    return rows


def _product_card(db: Session, product, company) -> BuyerProductCard:
    latest = product_price_repo.get_latest_price(db, product.id)
    price = float(latest.price) if latest else 0.0
    currency = latest.currency if latest else "EUR"
    return BuyerProductCard(
        product_id=product.id,
        product_name=product.product_name,
        admin_sku=product.admin_sku,
        image_url=f"https://picsum.photos/seed/urbyn-product-{product.id}/480/480",
        price=price,
        currency=currency,
        company_name=company.company_name if company else None,
        mandatory_attributes=_mandatory_out(product.id, db),
    )


def list_root_catalogs(db: Session, session: PortalSession) -> list[CatalogOut]:
    _require_client_session(db, session)
    return [_catalog_out(db, c) for c in buyer_repo.list_active_root_catalogs(db)]


def get_catalog_navigation(
    db: Session,
    session: PortalSession,
    catalog_id: int,
) -> BuyerCatalogNavigation:
    _require_client_session(db, session)
    catalog = repo.get_catalog(db, catalog_id)
    if catalog is None or not catalog.is_active:
        raise ClientPortalError("not_found", "Catalogue introuvable.")

    children = buyer_repo.list_active_catalog_children(db, catalog_id)
    breadcrumb_catalogs = buyer_repo.build_breadcrumb_chain(db, catalog)

    return BuyerCatalogNavigation(
        catalog=_catalog_out(db, catalog),
        children=[
            BuyerCatalogNavItem(
                id=child.id,
                name=child.name,
                has_children=buyer_repo.has_active_children(db, child.id),
            )
            for child in children
        ],
        breadcrumb=[_catalog_out(db, c) for c in breadcrumb_catalogs],
    )


def list_catalog_products(
    db: Session,
    session: PortalSession,
    catalog_id: int,
) -> list[BuyerProductCard]:
    _require_client_session(db, session)
    catalog = repo.get_catalog(db, catalog_id)
    if catalog is None or not catalog.is_active:
        raise ClientPortalError("not_found", "Catalogue introuvable.")

    leaf_ids = buyer_repo.collect_leaf_catalog_ids(db, catalog_id)
    rows = buyer_repo.list_marketplace_products_in_catalogs(db, leaf_ids)
    return [_product_card(db, product, company) for product, company in rows]


def get_product_card(
    db: Session,
    session: PortalSession,
    product_id: int,
) -> BuyerProductCard:
    _require_client_session(db, session)
    product = db.get(Product, product_id)
    if product is None or not product.is_active:
        raise ClientPortalError("not_found", "Produit introuvable.")
    company = db.get(Company, product.company_tva_intra_com)
    return _product_card(db, product, company)


def search_catalog_and_products(
    db: Session,
    session: PortalSession,
    query: str,
    limit: int = 20,
) -> list[BuyerSearchHit]:
    _require_client_session(db, session)
    q = query.strip()
    if len(q) < 2:
        return []

    per_type = max(1, limit // 2)
    hits: list[BuyerSearchHit] = []

    for catalog in buyer_repo.search_active_catalogs(db, q, limit=per_type):
        hits.append(
            BuyerSearchHit(
                type="catalog",
                id=catalog.id,
                label=catalog.name or f"Catalogue #{catalog.id}",
                breadcrumb=repo.get_breadcrumb(db, catalog),
            )
        )

    for product in buyer_repo.search_active_products(db, q, limit=per_type):
        hits.append(
            BuyerSearchHit(
                type="product",
                id=product.id,
                label=product.product_name,
                breadcrumb=[],
            )
        )

    hits.sort(key=lambda h: h.label.lower())
    return hits[:limit]


def get_product_detail(
    db: Session,
    session: PortalSession,
    product_id: int,
) -> BuyerProductDetail:
    _require_client_session(db, session)
    product = db.scalar(
        select(Product)
        .options(joinedload(Product.translations), joinedload(Product.company))
        .where(Product.id == product_id)
    )
    if product is None or not product.is_active:
        raise ClientPortalError("not_found", "Produit introuvable.")
    company = product.company
    translation = product.translations[0] if product.translations else None

    catalog_ids = repo.get_product_catalog_ids(db, product.id)
    breadcrumb: list[str] = []
    if catalog_ids:
        cat = repo.get_catalog(db, catalog_ids[0])
        if cat:
            breadcrumb = repo.get_breadcrumb(db, cat)

    shipping_options = [
        BuyerShippingOption(
            rate_id=r.id,
            carrier_name=r.carrier_name or "Transporteur",
            zone_from=r.zone_from or "",
            zone_to=r.zone_to or "",
            base_rate=float(r.base_rate or 0),
            currency=r.currency or "EUR",
        )
        for r in buyer_shipping.list_active_shipping_rates(db, product.company_tva_intra_com)
    ]

    card = _product_card(db, product, company)
    free_attrs = [
        ProductAttributeOut(id=a.id, name=a.name, value=a.value)
        for a in repo.list_product_attributes(db, product.id)
    ]

    return BuyerProductDetail(
        **card.model_dump(),
        short_description=translation.short_description if translation else None,
        description=translation.description if translation else None,
        free_attributes=free_attrs,
        stock_label=buyer_shipping.infer_stock_label(db, product.id),
        seller_company_tva=product.company_tva_intra_com,
        shipping_options=shipping_options,
        catalog_breadcrumb=breadcrumb,
    )


def check_shipping(
    db: Session,
    payload: ShippingCheckRequest,
) -> ShippingCheckResponse:
    session = PortalSession(user_id=payload.user_id, email=payload.email)
    _require_client_session(db, session)
    product = db.get(Product, payload.product_id)
    if product is None or not product.is_active:
        raise ClientPortalError("not_found", "Produit introuvable.")

    rate = buyer_shipping.find_matching_rate(
        db,
        product.company_tva_intra_com,
        zip_code=payload.zip_code,
        city=payload.city,
        state=payload.state,
        country_code=payload.country_code,
    )
    if rate is None:
        return ShippingCheckResponse(
            in_delivery_zone=False,
            message=(
                "Cette adresse est hors zone de livraison standard. "
                "Demandez un devis personnalisé."
            ),
        )
    return ShippingCheckResponse(
        in_delivery_zone=True,
        matched_rate_id=rate.id,
        carrier_name=rate.carrier_name,
        zone_label=rate.zone_to,
        shipping_price=float(rate.base_rate or 0),
        currency=rate.currency or "EUR",
        message="Livraison disponible au tarif annoncé pour cette zone.",
    )


def request_shipping_quote(db: Session, payload: ShippingQuoteRequest) -> dict:
    from app.services.email_sender import send_shipping_quote_email

    session = PortalSession(user_id=payload.user_id, email=payload.email)
    ctx = _require_client_session(db, session)
    product = db.get(Product, payload.product_id)
    if product is None or not product.is_active:
        raise ClientPortalError("not_found", "Produit introuvable.")
    company = db.get(Company, product.company_tva_intra_com)

    send_shipping_quote_email(
        buyer_email=str(payload.email),
        buyer_company=ctx.company_name,
        product_name=product.product_name,
        product_id=product.id,
        quantity=payload.quantity,
        seller_company=company.company_name if company else product.company_tva_intra_com,
        delivery_street=payload.delivery_street,
        delivery_zip_code=payload.delivery_zip_code,
        delivery_city=payload.delivery_city,
        delivery_state=payload.delivery_state,
        buyer_message=payload.buyer_message,
    )
    return {"message": "Votre demande de devis a été envoyée."}


def _cart_out(db: Session, cart) -> CartOut:
    items: list[CartItemOut] = []
    subtotal = 0.0
    count = 0
    for item in cart.items:
        line_total = float(item.unit_price) * item.quantity
        subtotal += line_total
        count += item.quantity
        product = item.product
        company = product.company if product else None
        items.append(
            CartItemOut(
                id=item.id,
                product_id=item.product_id,
                product_name=product.product_name if product else f"Produit #{item.product_id}",
                image_url=f"https://picsum.photos/seed/urbyn-product-{item.product_id}/480/480",
                seller_company_tva=item.seller_company_tva,
                seller_company_name=company.company_name if company else None,
                quantity=item.quantity,
                unit_price=float(item.unit_price),
                line_total=line_total,
                currency=item.currency,
            )
        )
    return CartOut(
        cart_id=cart.id,
        status=cart.status,
        currency=cart.currency,
        items=items,
        subtotal=round(subtotal, 2),
        item_count=count,
    )


def get_cart(db: Session, session: PortalSession) -> CartOut:
    ctx = _require_client_session(db, session)
    cart = cart_repo.get_open_cart(db, ctx.user_id)
    if cart is None:
        return CartOut(cart_id=0, status="open", currency="EUR", items=[], subtotal=0, item_count=0)
    cart = cart_repo.load_cart_with_items(db, cart.id)
    assert cart is not None
    return _cart_out(db, cart)


def add_to_cart(
    db: Session,
    session: PortalSession,
    *,
    product_id: int,
    quantity: int,
) -> CartOut:
    ctx = _require_client_session(db, session)
    product = db.get(Product, product_id)
    if product is None or not product.is_active:
        raise ClientPortalError("not_found", "Produit introuvable.")
    latest = product_price_repo.get_latest_price(db, product.id)
    currency = latest.currency if latest else "EUR"
    cart = cart_repo.get_or_create_open_cart(db, ctx.user_id, currency=currency)
    cart_repo.add_or_update_item(db, cart=cart, product=product, quantity=quantity)
    db.commit()
    cart = cart_repo.load_cart_with_items(db, cart.id)
    assert cart is not None
    return _cart_out(db, cart)


def update_cart_item(
    db: Session,
    session: PortalSession,
    *,
    item_id: int,
    quantity: int,
) -> CartOut:
    ctx = _require_client_session(db, session)
    cart = cart_repo.get_open_cart(db, ctx.user_id)
    if cart is None:
        raise ClientPortalError("not_found", "Panier introuvable.")
    item = cart_repo.get_cart_item(db, cart.id, item_id)
    if item is None:
        raise ClientPortalError("not_found", "Ligne panier introuvable.")
    if quantity <= 0:
        cart_repo.delete_item(db, item)
    else:
        cart_repo.update_item_quantity(db, item, quantity)
    db.commit()
    cart = cart_repo.load_cart_with_items(db, cart.id)
    assert cart is not None
    return _cart_out(db, cart)


def remove_cart_item(db: Session, session: PortalSession, *, item_id: int) -> CartOut:
    ctx = _require_client_session(db, session)
    cart = cart_repo.get_open_cart(db, ctx.user_id)
    if cart is None:
        raise ClientPortalError("not_found", "Panier introuvable.")
    item = cart_repo.get_cart_item(db, cart.id, item_id)
    if item is None:
        raise ClientPortalError("not_found", "Ligne panier introuvable.")
    cart_repo.delete_item(db, item)
    db.commit()
    cart = cart_repo.load_cart_with_items(db, cart.id)
    assert cart is not None
    return _cart_out(db, cart)


def get_cart_snapshot(db: Session, session: PortalSession) -> CartSnapshotOut:
    ctx = _require_client_session(db, session)
    cart = cart_repo.get_or_create_open_cart(db, ctx.user_id)
    db.commit()
    return CartSnapshotOut(
        cart_id=cart.id,
        items=cart_repo.get_cart_front_items(cart),
        updated_at=cart.updated_at,
    )


def put_cart_snapshot(
    db: Session,
    session: PortalSession,
    *,
    items: list[dict],
) -> CartSnapshotOut:
    ctx = _require_client_session(db, session)
    cart = cart_repo.get_or_create_open_cart(db, ctx.user_id)
    # Garde-fou taille : panier configurateur raisonnable
    if len(items) > 200:
        raise ClientPortalError("payload_too_large", "Panier trop volumineux.")
    cart_repo.save_cart_front_payload(db, cart, items)
    db.commit()
    db.refresh(cart)
    return CartSnapshotOut(
        cart_id=cart.id,
        items=cart_repo.get_cart_front_items(cart),
        updated_at=cart.updated_at,
    )


_POIDS_ATTR_NAMES = frozenset({"poids", "poids net", "poids_net"})
_DIMENSION_ATTR_MAP = {
    "longueur": "longueur",
    "largeur": "largeur",
    "hauteur": "hauteur",
    "profondeur": "profondeur",
    "volume": "volume",
}


def _normalize_attr_name(name: str | None) -> str:
    """Normalise un libellé d'attribut CSV/DB (casse, _, unités entre parenthèses)."""
    cleaned = (name or "").strip().lower().replace("_", " ")
    # « Largeur (cm) », « Poids (kg) », « Volume (m3) » → racine sans unité
    cleaned = re.sub(r"\s*\([^)]*\)\s*", " ", cleaned)
    return " ".join(cleaned.split())


def _is_poids_attribute(name: str | None) -> bool:
    normalized = _normalize_attr_name(name)
    return normalized in _POIDS_ATTR_NAMES or normalized.startswith("poids ")


def _dimension_field(name: str | None) -> str | None:
    normalized = _normalize_attr_name(name)
    # Ne pas confondre « Longueur panneau imprimé » avec « Longueur (cm) »
    if "panneau" in normalized:
        return None
    if normalized in _DIMENSION_ATTR_MAP:
        return _DIMENSION_ATTR_MAP[normalized]
    return None


def _parse_numeric_value(raw: str | None) -> float | None:
    if raw is None:
        return None
    token = raw.strip().replace(",", ".")
    if not token:
        return None
    for suffix in (
        "mm",
        "cm",
        "m",
        "kg",
        "kgs",
        "m3",
        "m³",
        "l",
        "litre",
        "litres",
    ):
        if token.lower().endswith(suffix):
            token = token[: -len(suffix)].strip()
            break
    try:
        return float(token)
    except ValueError:
        return None


def _parse_weight_value(raw: str | None) -> float | None:
    return _parse_numeric_value(raw)


def _dims_from_attr_rows(
    mandatory_rows: list,
    free_attrs: list,
) -> ProductDimensionsOut:
    dims: dict[str, float | None] = {
        "longueur": None,
        "largeur": None,
        "hauteur": None,
        "profondeur": None,
        "volume": None,
    }

    def _apply(name: str | None, value: str | None) -> None:
        field = _dimension_field(name)
        if field is None or dims[field] is not None:
            return
        parsed = _parse_numeric_value(value)
        if parsed is not None:
            dims[field] = parsed

    for val, defn in mandatory_rows:
        _apply(defn.attribute_name, val.value)
    for attr in free_attrs:
        _apply(attr.name, attr.value)
    return ProductDimensionsOut(**dims)


def _weight_from_attr_rows(mandatory_rows: list, free_attrs: list) -> float | None:
    for val, defn in mandatory_rows:
        if _is_poids_attribute(defn.attribute_name):
            parsed = _parse_weight_value(val.value)
            if parsed is not None:
                return parsed
    for attr in free_attrs:
        if _is_poids_attribute(attr.name):
            parsed = _parse_weight_value(attr.value)
            if parsed is not None:
                return parsed
    return None


def _attr_map_from_free(free_attrs: list) -> dict[str, str]:
    out: dict[str, str] = {}
    for attr in free_attrs:
        name = (attr.name or "").strip()
        value = (attr.value or "").strip()
        if name and value:
            out[name] = value
    return out


def _mandatory_out_from_rows(
    mandatory_rows: list,
    *,
    catalog_id: int | None = None,
) -> list[MandatoryAttributeValueOut]:
    rows: list[MandatoryAttributeValueOut] = []
    for val, defn in mandatory_rows:
        if catalog_id is not None and defn.catalog_id != catalog_id:
            continue
        rows.append(
            MandatoryAttributeValueOut(
                definition_id=defn.id,
                catalog_id=defn.catalog_id,
                attribute_name=defn.attribute_name,
                value=val.value,
            )
        )
    return rows


def _load_product_attr_bundle(db: Session, product_ids: list[int]) -> tuple[
    dict[int, list],
    dict[int, list],
    dict[int, object],
]:
    """Charge mandatory attrs + free attrs + latest prices en 3 requêtes."""
    ids = sorted({int(pid) for pid in product_ids if pid})
    if not ids:
        return {}, {}, {}
    mandatory = repo.list_mandatory_attribute_values_for_products(db, ids)
    free = repo.list_product_attributes_for_products(db, ids)
    prices = product_price_repo.get_latest_prices_for_products(db, ids)
    return mandatory, free, prices


def _product_dimensions(db: Session, product_id: int) -> ProductDimensionsOut:
    mandatory = repo.list_mandatory_attribute_values(db, product_id)
    free = repo.list_product_attributes(db, product_id)
    return _dims_from_attr_rows(mandatory, free)


def _product_weight_kg(db: Session, product_id: int) -> float | None:
    mandatory = repo.list_mandatory_attribute_values(db, product_id)
    free = repo.list_product_attributes(db, product_id)
    return _weight_from_attr_rows(mandatory, free)


def search_products_by_weight(
    db: Session,
    payload: ProductWeightFilterRequest,
) -> ProductWeightFilterResponse:
    if payload.poids_min > payload.poids_max:
        raise ClientPortalError(
            "invalid_range",
            "poids_min doit être inférieur ou égal à poids_max.",
        )

    leaf_ids = buyer_repo.collect_leaf_ids_for_catalog_refs(db, payload.catalog)
    rows = buyer_repo.get_product_catalog_links_in_catalogs(db, leaf_ids)

    unique_products: list = []
    seen: set[int] = set()
    meta: dict[int, tuple] = {}
    for product, company, catalog in rows:
        if product.id in seen:
            continue
        seen.add(product.id)
        unique_products.append(product)
        meta[product.id] = (company, catalog)

    mandatory, free, prices = _load_product_attr_bundle(
        db, [p.id for p in unique_products]
    )

    products: list[ProductWeightFilterItem] = []
    for product in unique_products:
        weight = _weight_from_attr_rows(
            mandatory.get(product.id, []), free.get(product.id, [])
        )
        if weight is None:
            continue
        if weight < payload.poids_min or weight > payload.poids_max:
            continue
        company, catalog = meta[product.id]
        latest = prices.get(product.id)
        products.append(
            ProductWeightFilterItem(
                product_id=product.id,
                product_name=product.product_name,
                admin_sku=product.admin_sku,
                poids=weight,
                dimensions=_dims_from_attr_rows(
                    mandatory.get(product.id, []), free.get(product.id, [])
                ),
                price=float(latest.price) if latest else 0.0,
                currency=latest.currency if latest else "EUR",
                company_name=company.company_name if company else None,
                catalog_id=catalog.id,
                catalog_name=catalog.name,
            )
        )

    return ProductWeightFilterResponse(
        catalog_leaf_ids=leaf_ids,
        count=len(products),
        products=products,
    )


def _resolve_massif_root(db: Session, root_name: str):
    root = buyer_repo.find_active_root_catalog_by_name(db, root_name)
    if root is not None:
        return root
    aliases = (
        "Massif_Type",
        "Massif Type",
        root_name.replace(" ", "_"),
        root_name.replace("_", " "),
    )
    for alias in aliases:
        if alias == root_name:
            continue
        root = buyer_repo.find_active_root_catalog_by_name(db, alias)
        if root is not None:
            return root
    return None


def list_massif_leaf_catalogs(
    db: Session,
    root_name: str = MASSIF_ROOT_DEFAULT,
    *,
    poids_min: float | None = None,
    poids_max: float | None = None,
) -> MassifLeafCatalogsResponse:
    root = _resolve_massif_root(db, root_name)
    if root is None:
        raise ClientPortalError(
            "not_found",
            f"Catalogue racine « {root_name} » introuvable.",
        )

    if poids_min is not None and poids_max is not None and poids_min > poids_max:
        raise ClientPortalError(
            "invalid_range",
            "poids_min doit être inférieur ou égal à poids_max.",
        )

    leaves = buyer_repo.collect_leaf_catalogs(db, root.id)
    catalogs: list[MassifLeafCatalogOut] = []
    for leaf in leaves:
        if poids_min is not None and poids_max is not None:
            if not _leaf_has_products_in_weight_range(db, leaf.id, poids_min, poids_max):
                continue
        catalogs.append(
            MassifLeafCatalogOut(
                id=leaf.id,
                name=leaf.name,
                description=leaf.description,
                parent_id=leaf.parent_id,
                breadcrumb=repo.get_breadcrumb(db, leaf),
            )
        )
    catalogs.sort(key=lambda c: (c.name or "").casefold())
    return MassifLeafCatalogsResponse(
        root_id=root.id,
        root_name=root.name or root_name,
        count=len(catalogs),
        catalogs=catalogs,
    )


def _leaf_has_products_in_weight_range(
    db: Session,
    catalog_id: int,
    poids_min: float,
    poids_max: float,
) -> bool:
    rows = buyer_repo.get_product_catalog_links_in_catalogs(db, [catalog_id])
    product_ids = []
    seen: set[int] = set()
    for product, _company, _cat in rows:
        if product.id in seen:
            continue
        seen.add(product.id)
        product_ids.append(product.id)
    if not product_ids:
        return False
    mandatory, free, _prices = _load_product_attr_bundle(db, product_ids)
    for pid in product_ids:
        weight = _weight_from_attr_rows(mandatory.get(pid, []), free.get(pid, []))
        if weight is None:
            continue
        if poids_min <= weight <= poids_max:
            return True
    return False


def list_massif_available_weight_bands(
    db: Session,
    root_name: str = MASSIF_ROOT_DEFAULT,
    bands: list[tuple[float, float]] | None = None,
) -> MassifWeightBandsResponse:
    """Indique quelles fourchettes de poids ont au moins un produit sous Massif Type."""
    root = _resolve_massif_root(db, root_name)
    if root is None:
        raise ClientPortalError(
            "not_found",
            f"Catalogue racine « {root_name} » introuvable.",
        )

    default_bands = bands or [
        (0.0, 299.0),
        (300.0, 750.0),
        (751.0, 1500.0),
        (1501.0, 2500.0),
        (2501.0, 99999.0),
    ]
    leaf_ids = buyer_repo.collect_leaf_catalog_ids(db, root.id)
    rows = buyer_repo.get_product_catalog_links_in_catalogs(db, leaf_ids)
    product_ids: list[int] = []
    seen: set[int] = set()
    for product, _company, _cat in rows:
        if product.id in seen:
            continue
        seen.add(product.id)
        product_ids.append(product.id)

    mandatory, free, _prices = _load_product_attr_bundle(db, product_ids)
    weights: list[float] = []
    for pid in product_ids:
        w = _weight_from_attr_rows(mandatory.get(pid, []), free.get(pid, []))
        if w is not None:
            weights.append(w)

    out: list[MassifWeightBandOut] = []
    for mn, mx in default_bands:
        count = sum(1 for w in weights if mn <= w <= mx)
        out.append(
            MassifWeightBandOut(
                poids_min=mn,
                poids_max=mx,
                product_count=count,
                available=count > 0,
            )
        )
    return MassifWeightBandsResponse(
        root_id=root.id,
        root_name=root.name or root_name,
        bands=out,
    )


def _resolve_massif_weight_range(payload: MassifProductsRequest) -> tuple[float, float]:
    if payload.poids is not None:
        return payload.poids, payload.poids
    if payload.poids_min is None or payload.poids_max is None:
        raise ClientPortalError(
            "invalid_range",
            "Fournissez poids (exact) ou le couple poids_min / poids_max.",
        )
    if payload.poids_min > payload.poids_max:
        raise ClientPortalError(
            "invalid_range",
            "poids_min doit être inférieur ou égal à poids_max.",
        )
    return payload.poids_min, payload.poids_max


def list_massif_products(
    db: Session,
    payload: MassifProductsRequest,
    root_name: str = MASSIF_ROOT_DEFAULT,
) -> MassifProductsResponse:
    poids_min, poids_max = _resolve_massif_weight_range(payload)

    root = _resolve_massif_root(db, root_name)
    if root is None:
        raise ClientPortalError(
            "not_found",
            f"Catalogue racine « {root_name} » introuvable.",
        )

    leaf_ids = set(buyer_repo.collect_leaf_catalog_ids(db, root.id))
    if payload.catalog_id not in leaf_ids:
        raise ClientPortalError(
            "invalid_catalog",
            f"Le catalogue choisi n'est pas une feuille sous « {root_name} ».",
        )

    catalog = repo.get_catalog(db, payload.catalog_id)
    if catalog is None or not catalog.is_active:
        raise ClientPortalError("not_found", "Catalogue introuvable.")

    rows = buyer_repo.get_product_catalog_links_in_catalogs(db, [payload.catalog_id])
    unique: list = []
    seen: set[int] = set()
    row_meta: dict[int, tuple] = {}
    for product, company, cat in rows:
        if product.id in seen:
            continue
        seen.add(product.id)
        unique.append(product)
        row_meta[product.id] = (company, cat)

    mandatory, free, prices = _load_product_attr_bundle(db, [p.id for p in unique])
    origin_cache: dict[int, tuple[str, str | None, int | None]] = {}

    products: list[MassifProductOut] = []
    for product in unique:
        weight = _weight_from_attr_rows(
            mandatory.get(product.id, []), free.get(product.id, [])
        )
        if weight is None or weight < poids_min or weight > poids_max:
            continue
        company, cat = row_meta[product.id]
        latest = prices.get(product.id)
        free_attrs = [
            ProductAttributeOut(id=a.id, name=a.name, value=a.value)
            for a in free.get(product.id, [])
        ]
        company_zip = company_city = company_country = None
        if company is not None:
            if product.id not in origin_cache:
                origin_cache[product.id] = resolve_product_origin_zip(db, product)
            company_zip, company_city, _addr_id = origin_cache[product.id]
            company_country = "FR"
        products.append(
            MassifProductOut(
                product_id=product.id,
                product_name=product.product_name,
                admin_sku=product.admin_sku,
                description=_product_description(db, product),
                poids=weight,
                dimensions=_dims_from_attr_rows(
                    mandatory.get(product.id, []), free.get(product.id, [])
                ),
                price=float(latest.price) if latest else 0.0,
                currency=latest.currency if latest else "EUR",
                company_name=company.company_name if company else None,
                company_tva=company.tva_intra_com if company else None,
                company_zip=company_zip,
                company_city=company_city,
                company_country=company_country,
                catalog_id=cat.id,
                catalog_name=cat.name,
                mandatory_attributes=_mandatory_out_from_rows(
                    mandatory.get(product.id, []),
                    catalog_id=payload.catalog_id,
                ),
                free_attributes=free_attrs,
            )
        )

    products.sort(key=lambda p: (p.product_name or "").casefold())
    return MassifProductsResponse(
        catalog_id=catalog.id,
        catalog_name=catalog.name,
        poids_min=poids_min,
        poids_max=poids_max,
        count=len(products),
        products=products,
    )


def _norm_manille_type(value: str | None) -> str:
    return " ".join((value or "").strip().lower().replace(" ", "").split())


def _resolve_massif_accessoire_catalog(db: Session):
    """Feuille « Accessoire » sous la racine « Massif » ([Massif/Accessoire])."""
    root = buyer_repo.find_active_root_catalog_by_name(db, "Massif")
    if root is None:
        return None, None
    for child in buyer_repo.list_active_catalog_children(db, root.id):
        if _norm_offer(child.name or "") == "accessoire":
            return root, child
    return root, None


def list_massif_manilles(db: Session) -> MassifManillesResponse:
    """Manilles du catalogue [Massif/Accessoire], indexées par attribut « Manille Type »."""
    root, accessoire = _resolve_massif_accessoire_catalog(db)
    if root is None or accessoire is None:
        raise ClientPortalError(
            "not_found",
            "Catalogue « Massif / Accessoire » introuvable.",
        )

    rows = buyer_repo.get_product_catalog_links_in_catalogs(db, [accessoire.id])
    products = []
    companies = {}
    seen: set[int] = set()
    for product, company, _cat in rows:
        if product.id in seen:
            continue
        seen.add(product.id)
        products.append(product)
        companies[product.id] = company

    mandatory, free, prices = _load_product_attr_bundle(db, [p.id for p in products])
    manilles: list[MassifManilleOut] = []
    for product in products:
        attrs = _attr_map_from_free(free.get(product.id, []))
        # merge mandatory names too (rare but cheap)
        for val, defn in mandatory.get(product.id, []):
            name = (defn.attribute_name or "").strip()
            value = (val.value or "").strip()
            if name and value and name not in attrs:
                attrs[name] = value
        manille_type = None
        for key, val in attrs.items():
            compact = key.casefold().replace(" ", "")
            if compact in {"manilletype", "manille_type"}:
                manille_type = val.strip()
                break
            if "manille" in key.casefold() and "type" in key.casefold():
                manille_type = val.strip()
                break
        if not manille_type:
            continue
        name_cf = (product.product_name or "").casefold()
        if "manille" not in name_cf:
            continue
        latest = prices.get(product.id)
        company = companies.get(product.id)
        manilles.append(
            MassifManilleOut(
                product_id=product.id,
                product_name=product.product_name,
                admin_sku=product.admin_sku,
                description=_product_description(db, product),
                manille_type=manille_type,
                price=float(latest.price) if latest else 0.0,
                currency=latest.currency if latest else "EUR",
                company_name=company.company_name if company else None,
                company_tva=company.tva_intra_com if company else None,
                poids=_weight_from_attr_rows(
                    mandatory.get(product.id, []), free.get(product.id, [])
                ),
            )
        )

    manilles.sort(
        key=lambda m: (_norm_manille_type(m.manille_type), m.product_name.casefold())
    )
    return MassifManillesResponse(
        catalog_id=accessoire.id,
        catalog_path=[root.name or "Massif", accessoire.name or "Accessoire"],
        count=len(manilles),
        manilles=manilles,
    )


def get_massif_palette(db: Session) -> MassifPaletteResponse:
    """Produit « Palette » du catalogue [Massif/Accessoire]."""
    root, accessoire = _resolve_massif_accessoire_catalog(db)
    if root is None or accessoire is None:
        raise ClientPortalError(
            "not_found",
            "Catalogue « Massif / Accessoire » introuvable.",
        )

    rows = buyer_repo.get_product_catalog_links_in_catalogs(db, [accessoire.id])
    palette_out: MassifPaletteOut | None = None
    for product, company, _cat in rows:
        name_cf = (product.product_name or "").casefold().strip()
        if name_cf != "palette" and "palette" not in name_cf:
            continue
        # Éviter les faux positifs type « transpalette » dans une description produit
        if name_cf != "palette" and not name_cf.startswith("palette"):
            continue
        latest = product_price_repo.get_latest_price(db, product.id)
        palette_out = MassifPaletteOut(
            product_id=product.id,
            product_name=product.product_name,
            admin_sku=product.admin_sku,
            client_sku=product.client_sku,
            description=_product_description(db, product),
            price=float(latest.price) if latest else 0.0,
            currency=latest.currency if latest else "EUR",
            company_name=company.company_name if company else None,
            company_tva=company.tva_intra_com if company else None,
            poids=_product_weight_kg(db, product.id),
        )
        if name_cf == "palette":
            break

    return MassifPaletteResponse(
        catalog_id=accessoire.id,
        catalog_path=[root.name or "Massif", accessoire.name or "Accessoire"],
        palette=palette_out,
    )


def _resolve_totem_accessoire_catalog(db: Session):
    """Feuille « Accessoire » sous la racine « Totem » ([Totem/Accessoire])."""
    root = buyer_repo.find_active_root_catalog_by_name(db, "Totem")
    if root is None:
        return None, None
    for child in buyer_repo.list_active_catalog_children(db, root.id):
        if _norm_offer(child.name or "") == "accessoire":
            return root, child
    return root, None


def list_totem_ballasts(db: Session) -> TotemBallastsResponse:
    """Lests du catalogue [Totem/Accessoire] (ex. Lest 25 kg / LEST-001)."""
    root, accessoire = _resolve_totem_accessoire_catalog(db)
    if root is None or accessoire is None:
        raise ClientPortalError(
            "not_found",
            "Catalogue « Totem / Accessoire » introuvable.",
        )

    rows = buyer_repo.get_product_catalog_links_in_catalogs(db, [accessoire.id])
    products = []
    companies = {}
    seen: set[int] = set()
    for product, company, _cat in rows:
        if product.id in seen:
            continue
        seen.add(product.id)
        name_cf = (product.product_name or "").casefold()
        sku_cf = (getattr(product, "client_sku", None) or "").casefold()
        if not (
            "lest" in name_cf
            or "fonte" in name_cf
            or sku_cf.startswith("lest")
            or "25" in name_cf
        ):
            continue
        products.append(product)
        companies[product.id] = company

    mandatory, free, prices = _load_product_attr_bundle(db, [p.id for p in products])
    ballasts: list[TotemBallastOut] = []
    for product in products:
        latest = prices.get(product.id)
        company = companies.get(product.id)
        ballasts.append(
            TotemBallastOut(
                product_id=product.id,
                product_name=product.product_name,
                client_sku=getattr(product, "client_sku", None),
                admin_sku=product.admin_sku,
                description=_product_description(db, product),
                price=float(latest.price) if latest else 0.0,
                currency=latest.currency if latest else "EUR",
                poids=_weight_from_attr_rows(
                    mandatory.get(product.id, []), free.get(product.id, [])
                ),
                company_name=company.company_name if company else None,
                company_tva=company.tva_intra_com if company else None,
            )
        )

    def _sort_key(b: TotemBallastOut) -> tuple:
        w = b.poids if b.poids is not None else 9999.0
        return (abs(w - 25.0), b.price, b.product_name.casefold())

    ballasts.sort(key=_sort_key)
    default = next(
        (b for b in ballasts if b.poids is not None and abs(b.poids - 25.0) < 0.5),
        None,
    )
    if default is None and ballasts:
        default = ballasts[0]

    return TotemBallastsResponse(
        catalog_id=accessoire.id,
        catalog_path=[root.name or "Totem", accessoire.name or "Accessoire"],
        count=len(ballasts),
        default_ballast=default,
        ballasts=ballasts,
    )


def _primary_company_address(db: Session, company_tva: str):
    """Adresse principale (ou première) d'une société fournisseur."""
    return db.scalar(
        select(Address)
        .where(Address.company_tva_intra_com == company_tva)
        .order_by(Address.is_primary.desc(), Address.id.asc())
        .limit(1)
    )


def _catalog_ancestor_ids(db: Session, catalog_ids: set[int]) -> dict[int, int]:
    """Map catalog_id → profondeur (0 = catalogue direct du produit)."""
    if not catalog_ids:
        return {}
    depth_by_id: dict[int, int] = {cid: 0 for cid in catalog_ids}
    frontier = set(catalog_ids)
    depth = 0
    # Remonte les parents (parent_id == id ⇒ racine)
    while frontier and depth < 32:
        depth += 1
        rows = db.execute(
            select(Catalog.id, Catalog.parent_id).where(Catalog.id.in_(frontier))
        ).all()
        next_frontier: set[int] = set()
        for cid, parent_id in rows:
            if parent_id is None or parent_id == cid:
                continue
            if parent_id not in depth_by_id:
                depth_by_id[parent_id] = depth
                next_frontier.add(parent_id)
        frontier = next_frontier
    return depth_by_id


def _norm_company_name(name: str | None) -> str:
    return " ".join((name or "").casefold().split())


def _address_company_match_score(
    db: Session, product_company_tva: str, address_company_tva: str
) -> int | None:
    """0 = même TVA, 1 = même raison sociale (ex. Urbanize / URBANIZE), sinon None."""
    if address_company_tva == product_company_tva:
        return 0
    product_co = db.get(Company, product_company_tva)
    address_co = db.get(Company, address_company_tva)
    if not product_co or not address_co:
        return None
    p_name = _norm_company_name(product_co.company_name)
    a_name = _norm_company_name(address_co.company_name)
    if p_name and a_name and p_name == a_name:
        return 1
    return None


def _address_from_catalog_links(db: Session, product: Product) -> Address | None:
    """Résout l'adresse d'origine via association adresse↔catalogue (héritage parents).

    Matching fournisseur :
    1) même TVA produit/adresse
    2) sinon même raison sociale (évite le split Urbanize / URBANIZE à 2 TVA)
    Ne prend jamais l'adresse d'un autre fournisseur sur le même catalogue.
    """
    product_catalog_ids = set(
        db.scalars(
            select(CatalogProduct.catalog_id).where(
                CatalogProduct.product_id == product.id
            )
        ).all()
    )
    if not product_catalog_ids:
        return None

    depth_by_catalog = _catalog_ancestor_ids(db, product_catalog_ids)
    candidate_catalog_ids = list(depth_by_catalog.keys())
    rows = db.execute(
        select(Address, AddressCatalog.catalog_id)
        .join(AddressCatalog, AddressCatalog.address_id == Address.id)
        .where(AddressCatalog.catalog_id.in_(candidate_catalog_ids))
    ).all()
    if not rows:
        return None

    # Plus spécifique = profondeur min, puis meilleur match société, puis id adresse
    best: Address | None = None
    best_key: tuple[int, int, int] | None = None
    for addr, catalog_id in rows:
        score = _address_company_match_score(
            db, product.company_tva_intra_com, addr.company_tva_intra_com
        )
        if score is None:
            continue
        d = depth_by_catalog.get(catalog_id, 10**9)
        key = (d, score, addr.id)
        if best_key is None or key < best_key:
            best = addr
            best_key = key
    return best


def _product_origin_address(db: Session, product: Product) -> Address | None:
    """Origine expédition : catalogue associé → address_id produit → None (fallback 75015)."""
    via_catalog = _address_from_catalog_links(db, product)
    if via_catalog is not None:
        return via_catalog
    if product.address_id:
        addr = db.get(Address, product.address_id)
        if (
            addr is not None
            and addr.company_tva_intra_com == product.company_tva_intra_com
        ):
            return addr
    return None


def resolve_product_origin_zip(
    db: Session, product: Product
) -> tuple[str, str | None, int | None]:
    """(zip, city, address_id) — fallback Paris 75015 si aucune adresse référencée."""
    addr = _product_origin_address(db, product)
    if addr is not None and (addr.zip_code or "").strip():
        return (addr.zip_code or "").strip(), addr.city, addr.id
    return FALLBACK_ORIGIN_ZIP, FALLBACK_ORIGIN_CITY, None


def _norm_offer(offer: str) -> str:
    return " ".join((offer or "").strip().replace("_", " ").split()).casefold()


def _find_child_by_offer(db: Session, parent_id: int, offer: str):
    needle = _norm_offer(offer)
    for child in buyer_repo.list_active_catalog_children(db, parent_id):
        if _norm_offer(child.name or "") == needle:
            return child
    return None


def _product_attr_map(db: Session, product_id: int) -> dict[str, str]:
    out: dict[str, str] = {}
    for attr in repo.list_product_attributes(db, product_id):
        name = (attr.name or "").strip()
        value = (attr.value or "").strip()
        if name and value:
            out[name] = value
    return out


def _product_description(db: Session, product: Product) -> str | None:
    translations = getattr(product, "translations", None)
    if translations:
        for tr in translations:
            text = (getattr(tr, "description", None) or "").strip()
            if text:
                return text
    else:
        from app.models import ProductTranslation

        row = db.scalar(
            select(ProductTranslation.description).where(
                ProductTranslation.product_id == product.id
            ).limit(1)
        )
        if row and str(row).strip():
            return str(row).strip()
    attrs = _product_attr_map(db, product.id)
    for key in ("Description", "description"):
        if attrs.get(key):
            return attrs[key]
    return None


def _short_text(text: str | None, max_len: int = 160) -> str | None:
    if not text:
        return None
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


def _format_dim_number(value: float | None) -> str | None:
    if value is None:
        return None
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    text = f"{value:.1f}".replace(".", ",")
    return text.rstrip("0").rstrip(",") if "," in text else text


def _dimensions_label(dims: ProductDimensionsOut) -> str | None:
    longueur = dims.longueur
    hauteur = dims.hauteur
    profondeur = dims.profondeur if dims.profondeur is not None else dims.largeur
    parts: list[str] = []
    if longueur is not None:
        parts.append(f"L {_format_dim_number(longueur)} cm")
    if hauteur is not None:
        parts.append(f"H {_format_dim_number(hauteur)} cm")
    if profondeur is not None:
        parts.append(f"P {_format_dim_number(profondeur)} cm")
    return " x ".join(parts) if parts else None


def _product_body_dims_cm(
    attrs: dict[str, str],
    dims: ProductDimensionsOut | None = None,
) -> tuple[float | None, float | None, float | None]:
    """Longueur / Hauteur / Profondeur produit (pas les dims panneau)."""
    longueur = _parse_cm_value(_attr_ci(attrs, "Longueur (cm)", "Longueur"))
    hauteur = _parse_cm_value(_attr_ci(attrs, "Hauteur (cm)", "Hauteur"))
    profondeur = _parse_cm_value(_attr_ci(attrs, "Profondeur (cm)", "Profondeur"))
    if dims is not None:
        if longueur is None:
            longueur = dims.longueur
        if hauteur is None:
            hauteur = dims.hauteur
        if profondeur is None:
            profondeur = dims.profondeur if dims.profondeur is not None else dims.largeur
    return longueur, hauteur, profondeur


def _dimensions_label_from_product(
    attrs: dict[str, str],
    dims: ProductDimensionsOut | None = None,
) -> str | None:
    longueur, hauteur, profondeur = _product_body_dims_cm(attrs, dims)
    return _dimensions_label(
        ProductDimensionsOut(
            longueur=longueur,
            hauteur=hauteur,
            profondeur=profondeur,
            largeur=None,
            volume=None,
        )
    )


def _dims_sort_key(
    attrs: dict[str, str],
    dims: ProductDimensionsOut | None = None,
) -> tuple[float, float, float, float]:
    """Clé de tri : volume puis L/H/P (produit le plus petit)."""
    longueur, hauteur, profondeur = _product_body_dims_cm(attrs, dims)
    L = float(longueur or 0)
    H = float(hauteur or 0)
    P = float(profondeur or 0)
    volume = L * H * P if (L and H and P) else (L + H + P)
    return (volume if volume > 0 else float("inf"), L or float("inf"), H or float("inf"), P or float("inf"))


def _parse_detail_bullets(raw: str | None) -> list[str]:
    if not raw:
        return []
    bullets: list[str] = []
    for line in raw.replace("\r\n", "\n").split("\n"):
        text = line.strip()
        if not text:
            continue
        if text.startswith(("-", "•", "*")):
            text = text[1:].strip()
        if text:
            bullets.append(text)
    return bullets


def _attr_ci(attrs: dict[str, str], *names: str) -> str | None:
    normalized = {_normalize_attr_name(k): v for k, v in attrs.items()}
    for name in names:
        key = _normalize_attr_name(name)
        if key in normalized:
            return normalized[key]
    return None


def _parse_cm_value(raw: str | None) -> float | None:
    if not raw:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)", str(raw).replace(",", "."))
    if not m:
        return None
    try:
        n = float(m.group(1))
    except ValueError:
        return None
    return n if n > 0 else None


def _panel_print_dims_cm(attrs: dict[str, str]) -> tuple[float | None, float | None]:
    length = _parse_cm_value(
        _attr_ci(
            attrs,
            "Longueur panneau imprimé (cm)",
            "Longueur panneau imprimé",
            "Longueur panneau",
        )
    )
    height = _parse_cm_value(
        _attr_ci(
            attrs,
            "Hauteur panneau imprimé (cm)",
            "Hauteur panneau imprimé",
            "Hauteur panneau",
        )
    )
    return length, height


def _panel_format_label(attrs: dict[str, str]) -> str | None:
    length, height = _panel_print_dims_cm(attrs)
    if length is not None and height is not None:
        def _fmt(v: float) -> str:
            return str(int(v)) if abs(v - round(v)) < 1e-9 else str(v).replace(".", ",")

        return f"{_fmt(length)} × {_fmt(height)} cm"
    return _attr_ci(attrs, "Format panneau imprimé", "Format panneau")


def _catalog_product_rows(db: Session, catalog_id: int):
    return buyer_repo.get_product_catalog_links_in_catalogs(db, [catalog_id])


def _cheapest_product_meta(
    db: Session, catalog_id: int
) -> tuple[float, str, str | None, int, str | None]:
    """Retourne (min_price, currency, description, product_count, min_dimensions_label)."""
    rows = _catalog_product_rows(db, catalog_id)
    products = []
    seen: set[int] = set()
    for product, _company, _cat in rows:
        if product.id in seen:
            continue
        seen.add(product.id)
        products.append(product)
    if not products:
        return 0.0, "EUR", None, 0, None

    mandatory, free, prices = _load_product_attr_bundle(db, [p.id for p in products])
    min_price: float | None = None
    currency = "EUR"
    description: str | None = None
    smallest_key: tuple[float, float, float, float] | None = None
    min_dimensions_label: str | None = None
    for product in products:
        latest = prices.get(product.id)
        price = float(latest.price) if latest else 0.0
        cur = latest.currency if latest else "EUR"
        if min_price is None or price < min_price:
            min_price = price
            currency = cur
            description = _product_description(db, product)

        dims = _dims_from_attr_rows(mandatory.get(product.id, []), free.get(product.id, []))
        attrs = _attr_map_from_free(free.get(product.id, []))
        key = _dims_sort_key(attrs, dims)
        if smallest_key is None or key < smallest_key:
            smallest_key = key
            min_dimensions_label = _dimensions_label_from_product(attrs, dims)
    return (min_price or 0.0), currency, description, len(products), min_dimensions_label


def list_totem_families(
    db: Session,
    *,
    offer: str = "Acquisition",
    root_name: str = TOTEM_ROOT_DEFAULT,
) -> TotemFamiliesResponse:
    """
    Familles sous Totem pour une offre (Acquisition / Location).

    Structure CSV : Totem / {Famille} / {Acquisition|Location}
    Structure alt. : Totem / {Acquisition|Location} / {Famille}
    """
    root = buyer_repo.find_active_root_catalog_by_name(db, root_name)
    if root is None:
        raise ClientPortalError(
            "not_found",
            f"Catalogue racine « {root_name} » introuvable.",
        )

    families: list[TotemFamilyOut] = []
    seen_family_ids: set[int] = set()

    # Pattern A : Totem → Famille → Offer
    for family in buyer_repo.list_active_catalog_children(db, root.id):
        leaf = _find_child_by_offer(db, family.id, offer)
        if leaf is None:
            continue
        min_price, currency, description, count, min_dims = _cheapest_product_meta(
            db, leaf.id
        )
        if count == 0:
            continue
        seen_family_ids.add(family.id)
        raw_name = (family.name or "").strip() or "Totem"
        display = raw_name if raw_name.casefold().startswith("totem") else f"Totem {raw_name}"
        families.append(
            TotemFamilyOut(
                family_catalog_id=family.id,
                leaf_catalog_id=leaf.id,
                name=raw_name,
                display_name=display,
                description=_short_text(description),
                min_price=min_price,
                currency=currency,
                product_count=count,
                min_dimensions_label=min_dims,
                breadcrumb=repo.get_breadcrumb(db, leaf),
            )
        )

    # Pattern B : Totem → Offer → Famille (si rien trouvé en A, ou en complément)
    offer_node = _find_child_by_offer(db, root.id, offer)
    if offer_node is not None:
        for family in buyer_repo.list_active_catalog_children(db, offer_node.id):
            if family.id in seen_family_ids:
                continue
            # feuille directe ou sous-feuille unique
            leaf = family
            children = buyer_repo.list_active_catalog_children(db, family.id)
            if children:
                # si la famille a encore des enfants, on agrège le min sur toutes les feuilles
                leaf_ids = buyer_repo.collect_leaf_catalog_ids(db, family.id)
                min_price = None
                currency = "EUR"
                description = None
                count = 0
                min_dims: str | None = None
                best_dims_key: tuple[float, float, float, float] | None = None
                for lid in leaf_ids:
                    p, c, d, n, _leaf_dims = _cheapest_product_meta(db, lid)
                    if n == 0:
                        continue
                    count += n
                    if min_price is None or p < min_price:
                        min_price = p
                        currency = c
                        description = d
                    # Plus petit produit (dims) — une passe batchée par feuille
                    leaf_rows = _catalog_product_rows(db, lid)
                    leaf_pids = []
                    leaf_seen: set[int] = set()
                    for product, _company, _cat in leaf_rows:
                        if product.id in leaf_seen:
                            continue
                        leaf_seen.add(product.id)
                        leaf_pids.append(product.id)
                    leaf_mand, leaf_free, _leaf_prices = _load_product_attr_bundle(
                        db, leaf_pids
                    )
                    for pid in leaf_pids:
                        dims = _dims_from_attr_rows(
                            leaf_mand.get(pid, []), leaf_free.get(pid, [])
                        )
                        attrs = _attr_map_from_free(leaf_free.get(pid, []))
                        key = _dims_sort_key(attrs, dims)
                        if best_dims_key is None or key < best_dims_key:
                            best_dims_key = key
                            min_dims = _dimensions_label_from_product(attrs, dims)
                if count == 0:
                    continue
                leaf = children[0]
            else:
                min_price, currency, description, count, min_dims = _cheapest_product_meta(
                    db, family.id
                )
                if count == 0:
                    continue
            raw_name = (family.name or "").strip() or "Totem"
            display = (
                raw_name if raw_name.casefold().startswith("totem") else f"Totem {raw_name}"
            )
            families.append(
                TotemFamilyOut(
                    family_catalog_id=family.id,
                    leaf_catalog_id=leaf.id,
                    name=raw_name,
                    display_name=display,
                    description=_short_text(description),
                    min_price=min_price or 0.0,
                    currency=currency,
                    product_count=count,
                    min_dimensions_label=min_dims,
                    breadcrumb=repo.get_breadcrumb(db, leaf),
                )
            )

    families.sort(key=lambda f: f.display_name.casefold())
    return TotemFamiliesResponse(
        root_id=root.id,
        root_name=root.name or root_name,
        offer=offer,
        count=len(families),
        families=families,
    )


def list_totem_family_products(
    db: Session,
    *,
    family_catalog_id: int,
    offer: str = "Acquisition",
) -> TotemProductsResponse:
    family = repo.get_catalog(db, family_catalog_id)
    if family is None or not family.is_active:
        raise ClientPortalError("not_found", "Famille totem introuvable.")

    leaf = _find_child_by_offer(db, family.id, offer)
    if leaf is None:
        # Pattern B : la famille est déjà sous Offer, ou est elle-même la feuille
        if _norm_offer(family.name or "") == _norm_offer(offer):
            raise ClientPortalError(
                "invalid_catalog",
                f"Pas de produits pour l'offre « {offer} » sur cette famille.",
            )
        children = buyer_repo.list_active_catalog_children(db, family.id)
        if children:
            raise ClientPortalError(
                "not_found",
                f"Catalogue « {offer} » introuvable sous cette famille.",
            )
        leaf = family

    rows = _catalog_product_rows(db, leaf.id)
    products_raw = []
    seen: set[int] = set()
    for product, _company, _cat in rows:
        if product.id in seen:
            continue
        seen.add(product.id)
        products_raw.append(product)

    mandatory, free, prices = _load_product_attr_bundle(
        db, [p.id for p in products_raw]
    )
    products: list[TotemProductOut] = []
    for product in products_raw:
        latest = prices.get(product.id)
        dims = _dims_from_attr_rows(
            mandatory.get(product.id, []), free.get(product.id, [])
        )
        attrs = _attr_map_from_free(free.get(product.id, []))
        products.append(
            TotemProductOut(
                product_id=product.id,
                product_name=product.product_name,
                client_sku=product.client_sku,
                price=float(latest.price) if latest else 0.0,
                currency=latest.currency if latest else "EUR",
                dimensions_label=_dimensions_label_from_product(attrs, dims),
                dimensions=dims,
                poids=_weight_from_attr_rows(
                    mandatory.get(product.id, []), free.get(product.id, [])
                ),
                attributes=attrs,
            )
        )

    products.sort(key=lambda p: (p.price, p.product_name.casefold()))
    return TotemProductsResponse(
        family_catalog_id=family.id,
        leaf_catalog_id=leaf.id,
        family_name=(family.name or "").strip() or "Totem",
        offer=offer,
        count=len(products),
        products=products,
    )


def get_totem_product_detail(db: Session, product_id: int) -> TotemProductDetailOut:
    product = db.scalar(
        select(Product)
        .options(joinedload(Product.translations))
        .where(Product.id == product_id)
    )
    if product is None or not product.is_active:
        raise ClientPortalError("not_found", "Produit introuvable.")

    latest = product_price_repo.get_latest_price(db, product.id)
    dims = _product_dimensions(db, product.id)
    attrs = _product_attr_map(db, product.id)
    description = _product_description(db, product)
    detail_raw = _attr_ci(attrs, "Détail", "Detail", "Détails", "Details")
    fiche_key = (product.product_name or "").strip() or None
    fiche_available = False
    if fiche_key:
        import json
        from app.core.config import settings

        raw = (settings.FICHE_TECHNIQUE_DRIVE_MAP or "").strip()
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {}
        if isinstance(data, dict):
            keys = {str(k).strip().casefold() for k in data if str(k).strip()}
            fiche_available = fiche_key.casefold() in keys

    company = db.get(Company, product.company_tva_intra_com)
    origin_zip, origin_city, origin_address_id = resolve_product_origin_zip(db, product)

    return TotemProductDetailOut(
        product_id=product.id,
        product_name=product.product_name,
        client_sku=product.client_sku,
        price=float(latest.price) if latest else 0.0,
        currency=latest.currency if latest else "EUR",
        description=description,
        dimensions_label=_dimensions_label_from_product(attrs, dims),
        dimensions=dims,
        poids=_product_weight_kg(db, product.id),
        footprint=_attr_ci(attrs, "Encombrement au sol", "Encombrement"),
        panel_format=_panel_format_label(attrs),
        attributes=attrs,
        detail_bullets=_parse_detail_bullets(detail_raw),
        fiche_document_key=fiche_key,
        fiche_available=fiche_available,
        company_name=company.company_name if company else None,
        company_tva=product.company_tva_intra_com,
        company_zip=origin_zip,
        company_city=origin_city,
        origin_address_id=origin_address_id,
    )
