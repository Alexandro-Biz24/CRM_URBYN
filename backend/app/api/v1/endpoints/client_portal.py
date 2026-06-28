from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.client_portal import (
    BuyerCatalogNavigation,
    BuyerProductCard,
    BuyerProductDetail,
    BuyerSearchHit,
    CartItemAdd,
    CartItemUpdate,
    CartOut,
    CartSessionBody,
    ProductWeightFilterRequest,
    ProductWeightFilterResponse,
    ShippingCheckRequest,
    ShippingCheckResponse,
    ShippingQuoteRequest,
)
from app.schemas.supplier_portal import CatalogOut, PortalContext, PortalSession
from app.services.client_portal import (
    ClientPortalError,
    add_to_cart,
    check_shipping,
    get_cart,
    get_catalog_navigation,
    get_context,
    get_product_card,
    get_product_detail,
    list_catalog_products,
    list_root_catalogs,
    remove_cart_item,
    request_shipping_quote,
    search_catalog_and_products,
    search_products_by_weight,
    update_cart_item,
)

router = APIRouter()


def _http_error(exc: ClientPortalError) -> HTTPException:
    code = exc.code
    status_code = status.HTTP_400_BAD_REQUEST
    if code in ("session_mismatch",):
        status_code = status.HTTP_401_UNAUTHORIZED
    elif code in ("role_mismatch", "no_company"):
        status_code = status.HTTP_403_FORBIDDEN
    elif code in ("not_found",):
        status_code = status.HTTP_404_NOT_FOUND
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": exc.message},
    )


def _session(user_id: int = Query(...), email: str = Query(...)) -> PortalSession:
    return PortalSession(user_id=user_id, email=email)


@router.post("/context", response_model=PortalContext)
def portal_context(payload: PortalSession, db: Session = Depends(get_db)) -> PortalContext:
    try:
        return get_context(db, payload)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.get("/catalogs/roots", response_model=list[CatalogOut])
def portal_root_catalogs(
    session: PortalSession = Depends(_session),
    db: Session = Depends(get_db),
) -> list[CatalogOut]:
    try:
        return list_root_catalogs(db, session)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.get("/catalogs/{catalog_id}/navigation", response_model=BuyerCatalogNavigation)
def portal_catalog_navigation(
    catalog_id: int,
    session: PortalSession = Depends(_session),
    db: Session = Depends(get_db),
) -> BuyerCatalogNavigation:
    try:
        return get_catalog_navigation(db, session, catalog_id)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.get("/catalogs/{catalog_id}/products", response_model=list[BuyerProductCard])
def portal_catalog_products(
    catalog_id: int,
    session: PortalSession = Depends(_session),
    db: Session = Depends(get_db),
) -> list[BuyerProductCard]:
    try:
        return list_catalog_products(db, session, catalog_id)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.get("/search", response_model=list[BuyerSearchHit])
def portal_search(
    q: str = Query(..., min_length=2),
    limit: int = Query(20, ge=1, le=50),
    session: PortalSession = Depends(_session),
    db: Session = Depends(get_db),
) -> list[BuyerSearchHit]:
    try:
        return search_catalog_and_products(db, session, q, limit=limit)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.post("/products/search-by-weight", response_model=ProductWeightFilterResponse)
def portal_search_products_by_weight(
    payload: ProductWeightFilterRequest,
    db: Session = Depends(get_db),
) -> ProductWeightFilterResponse:
    """Filtre les produits des catalogues feuilles par fourchette de poids (attribut poids / poids_net)."""
    try:
        return search_products_by_weight(db, payload)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.get("/products/{product_id}", response_model=BuyerProductCard)
def portal_product_card(
    product_id: int,
    session: PortalSession = Depends(_session),
    db: Session = Depends(get_db),
) -> BuyerProductCard:
    try:
        return get_product_card(db, session, product_id)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.get("/products/{product_id}/detail", response_model=BuyerProductDetail)
def portal_product_detail(
    product_id: int,
    session: PortalSession = Depends(_session),
    db: Session = Depends(get_db),
) -> BuyerProductDetail:
    try:
        return get_product_detail(db, session, product_id)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.post("/shipping/check", response_model=ShippingCheckResponse)
def portal_shipping_check(
    payload: ShippingCheckRequest,
    db: Session = Depends(get_db),
) -> ShippingCheckResponse:
    try:
        return check_shipping(db, payload)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.post("/shipping/quote-request")
def portal_shipping_quote(
    payload: ShippingQuoteRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return request_shipping_quote(db, payload)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.get("/cart", response_model=CartOut)
def portal_get_cart(
    session: PortalSession = Depends(_session),
    db: Session = Depends(get_db),
) -> CartOut:
    try:
        return get_cart(db, session)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.post("/cart/items", response_model=CartOut)
def portal_add_cart_item(
    payload: CartItemAdd,
    db: Session = Depends(get_db),
) -> CartOut:
    try:
        session = PortalSession(user_id=payload.user_id, email=payload.email)
        return add_to_cart(db, session, product_id=payload.product_id, quantity=payload.quantity)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.patch("/cart/items/{item_id}", response_model=CartOut)
def portal_update_cart_item(
    item_id: int,
    payload: CartItemUpdate,
    db: Session = Depends(get_db),
) -> CartOut:
    try:
        session = PortalSession(user_id=payload.user_id, email=payload.email)
        return update_cart_item(db, session, item_id=item_id, quantity=payload.quantity)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.delete("/cart/items/{item_id}", response_model=CartOut)
def portal_delete_cart_item(
    item_id: int,
    session: PortalSession = Depends(_session),
    db: Session = Depends(get_db),
) -> CartOut:
    try:
        return remove_cart_item(db, session, item_id=item_id)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc
