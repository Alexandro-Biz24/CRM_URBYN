from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Company, Product
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
    # « longueur cm » après strip raté → prend le premier token connu
    if normalized in _DIMENSION_ATTR_MAP:
        return _DIMENSION_ATTR_MAP[normalized]
    first = normalized.split(" ", 1)[0] if normalized else ""
    return _DIMENSION_ATTR_MAP.get(first)


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


def _product_dimensions(db: Session, product_id: int) -> ProductDimensionsOut:
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

    for val, defn in repo.list_mandatory_attribute_values(db, product_id):
        _apply(defn.attribute_name, val.value)
    for attr in repo.list_product_attributes(db, product_id):
        _apply(attr.name, attr.value)

    return ProductDimensionsOut(**dims)


def _product_weight_kg(db: Session, product_id: int) -> float | None:
    for val, defn in repo.list_mandatory_attribute_values(db, product_id):
        if _is_poids_attribute(defn.attribute_name):
            parsed = _parse_weight_value(val.value)
            if parsed is not None:
                return parsed
    for attr in repo.list_product_attributes(db, product_id):
        if _is_poids_attribute(attr.name):
            parsed = _parse_weight_value(attr.value)
            if parsed is not None:
                return parsed
    return None


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

    products: list[ProductWeightFilterItem] = []
    seen: set[int] = set()

    for product, company, catalog in rows:
        if product.id in seen:
            continue
        weight = _product_weight_kg(db, product.id)
        if weight is None:
            continue
        if weight < payload.poids_min or weight > payload.poids_max:
            continue
        seen.add(product.id)
        latest = product_price_repo.get_latest_price(db, product.id)
        products.append(
            ProductWeightFilterItem(
                product_id=product.id,
                product_name=product.product_name,
                admin_sku=product.admin_sku,
                poids=weight,
                dimensions=_product_dimensions(db, product.id),
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
    seen: set[int] = set()
    for product, _company, _cat in rows:
        if product.id in seen:
            continue
        seen.add(product.id)
        weight = _product_weight_kg(db, product.id)
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
    weights: list[float] = []
    seen: set[int] = set()
    for product, _company, _cat in rows:
        if product.id in seen:
            continue
        seen.add(product.id)
        w = _product_weight_kg(db, product.id)
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
    products: list[MassifProductOut] = []
    seen: set[int] = set()

    for product, company, cat in rows:
        if product.id in seen:
            continue
        weight = _product_weight_kg(db, product.id)
        if weight is None:
            continue
        if weight < poids_min or weight > poids_max:
            continue
        seen.add(product.id)
        latest = product_price_repo.get_latest_price(db, product.id)
        free_attrs = [
            ProductAttributeOut(id=a.id, name=a.name, value=a.value)
            for a in repo.list_product_attributes(db, product.id)
        ]
        products.append(
            MassifProductOut(
                product_id=product.id,
                product_name=product.product_name,
                admin_sku=product.admin_sku,
                poids=weight,
                dimensions=_product_dimensions(db, product.id),
                price=float(latest.price) if latest else 0.0,
                currency=latest.currency if latest else "EUR",
                company_name=company.company_name if company else None,
                catalog_id=cat.id,
                catalog_name=cat.name,
                mandatory_attributes=_mandatory_out(
                    product.id, db, catalog_id=payload.catalog_id
                ),
                free_attributes=free_attrs,
            )
        )

    return MassifProductsResponse(
        catalog_id=catalog.id,
        catalog_name=catalog.name,
        poids_min=poids_min,
        poids_max=poids_max,
        count=len(products),
        products=products,
    )


# ── Totem ─────────────────────────────────────────────────────────────────────

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


def _catalog_product_rows(db: Session, catalog_id: int):
    return buyer_repo.get_product_catalog_links_in_catalogs(db, [catalog_id])


def _cheapest_product_meta(db: Session, catalog_id: int) -> tuple[float, str, str | None, int]:
    """Retourne (min_price, currency, description, product_count)."""
    rows = _catalog_product_rows(db, catalog_id)
    min_price: float | None = None
    currency = "EUR"
    description: str | None = None
    count = 0
    seen: set[int] = set()
    for product, _company, _cat in rows:
        if product.id in seen:
            continue
        seen.add(product.id)
        count += 1
        latest = product_price_repo.get_latest_price(db, product.id)
        price = float(latest.price) if latest else 0.0
        cur = latest.currency if latest else "EUR"
        if min_price is None or price < min_price:
            min_price = price
            currency = cur
            description = _product_description(db, product)
    return (min_price or 0.0), currency, description, count


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
        min_price, currency, description, count = _cheapest_product_meta(db, leaf.id)
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
                for lid in leaf_ids:
                    p, c, d, n = _cheapest_product_meta(db, lid)
                    if n == 0:
                        continue
                    count += n
                    if min_price is None or p < min_price:
                        min_price = p
                        currency = c
                        description = d
                if count == 0:
                    continue
                leaf = children[0]
            else:
                min_price, currency, description, count = _cheapest_product_meta(
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
        # Si pas d'enfant Offer, traiter family comme feuille
        children = buyer_repo.list_active_catalog_children(db, family.id)
        if children:
            raise ClientPortalError(
                "not_found",
                f"Catalogue « {offer} » introuvable sous cette famille.",
            )
        leaf = family

    rows = _catalog_product_rows(db, leaf.id)
    products: list[TotemProductOut] = []
    seen: set[int] = set()
    for product, _company, _cat in rows:
        if product.id in seen:
            continue
        seen.add(product.id)
        latest = product_price_repo.get_latest_price(db, product.id)
        dims = _product_dimensions(db, product.id)
        attrs = _product_attr_map(db, product.id)
        products.append(
            TotemProductOut(
                product_id=product.id,
                product_name=product.product_name,
                client_sku=product.client_sku,
                price=float(latest.price) if latest else 0.0,
                currency=latest.currency if latest else "EUR",
                dimensions_label=_dimensions_label(dims),
                dimensions=dims,
                poids=_product_weight_kg(db, product.id),
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

    return TotemProductDetailOut(
        product_id=product.id,
        product_name=product.product_name,
        client_sku=product.client_sku,
        price=float(latest.price) if latest else 0.0,
        currency=latest.currency if latest else "EUR",
        description=description,
        dimensions_label=_dimensions_label(dims),
        dimensions=dims,
        poids=_product_weight_kg(db, product.id),
        footprint=_attr_ci(attrs, "Encombrement au sol", "Encombrement"),
        panel_format=_attr_ci(attrs, "Format panneau imprimé", "Format panneau"),
        attributes=attrs,
        detail_bullets=_parse_detail_bullets(detail_raw),
        fiche_document_key=fiche_key,
        fiche_available=fiche_available,
    )
