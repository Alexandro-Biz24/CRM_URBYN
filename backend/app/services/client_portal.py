from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Company, Product
from app.repositories import cart_repo
from app.repositories import client_portal_repo as buyer_repo
from app.repositories import product_price_repo, supplier_portal_repo as repo
from app.services import buyer_shipping
from app.schemas.client_portal import (
    BuyerCatalogNavItem,
    BuyerCatalogNavigation,
    BuyerProductCard,
    BuyerProductDetail,
    BuyerSearchHit,
    BuyerShippingOption,
    CartItemOut,
    CartOut,
    ProductAttributeOut,
    ProductWeightFilterItem,
    ProductWeightFilterRequest,
    ProductWeightFilterResponse,
    ProductDimensionsOut,
    ShippingCheckRequest,
    ShippingCheckResponse,
    ShippingQuoteRequest,
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


def _mandatory_out(product_id: int, db: Session) -> list[MandatoryAttributeValueOut]:
    return [
        MandatoryAttributeValueOut(
            definition_id=defn.id,
            catalog_id=defn.catalog_id,
            attribute_name=defn.attribute_name,
            value=val.value,
        )
        for val, defn in repo.list_mandatory_attribute_values(db, product_id)
    ]


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


_POIDS_ATTR_NAMES = frozenset({"poids", "poids net", "poids_net"})
_DIMENSION_ATTR_MAP = {
    "longueur": "longueur",
    "largeur": "largeur",
    "hauteur": "hauteur",
    "volume": "volume",
}


def _normalize_attr_name(name: str | None) -> str:
    return (name or "").strip().lower().replace("_", " ")


def _is_poids_attribute(name: str | None) -> bool:
    normalized = _normalize_attr_name(name)
    return normalized in _POIDS_ATTR_NAMES or normalized.startswith("poids ")


def _dimension_field(name: str | None) -> str | None:
    normalized = _normalize_attr_name(name)
    return _DIMENSION_ATTR_MAP.get(normalized)


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
