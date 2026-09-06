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
    CartSnapshotOut,
    CartSnapshotPut,
    MassifLeafCatalogsResponse,
    MassifManillesResponse,
    MassifProductsRequest,
    MassifProductsResponse,
    MassifWeightBandsResponse,
    ProductWeightFilterRequest,
    ProductWeightFilterResponse,
    ShippingCheckRequest,
    ShippingCheckResponse,
    ShippingQuoteRequest,
    TotemBallastsResponse,
    TotemFamiliesResponse,
    TotemProductDetailOut,
    TotemProductsResponse,
    TotemWindSheetLookupRequest,
    TotemWindSheetLookupResponse,
)
from app.schemas.supplier_portal import CatalogOut, PortalContext, PortalSession
from app.services.client_portal import (
    ClientPortalError,
    add_to_cart,
    check_shipping,
    get_cart,
    get_cart_snapshot,
    get_catalog_navigation,
    get_context,
    get_product_card,
    get_product_detail,
    get_totem_product_detail,
    list_catalog_products,
    list_massif_available_weight_bands,
    list_massif_leaf_catalogs,
    list_massif_manilles,
    list_massif_products,
    list_root_catalogs,
    list_totem_ballasts,
    list_totem_families,
    list_totem_family_products,
    put_cart_snapshot,
    remove_cart_item,
    request_shipping_quote,
    search_catalog_and_products,
    search_products_by_weight,
    update_cart_item,
)
from app.services.totem_wind_sheet import TotemWindSheetError, lookup_totem_wind_sheet

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


@router.get("/massif/leaf-catalogs", response_model=MassifLeafCatalogsResponse)
def portal_massif_leaf_catalogs(
    root_name: str = Query("Massif Type", min_length=1),
    poids_min: float | None = Query(None, ge=0),
    poids_max: float | None = Query(None, ge=0),
    db: Session = Depends(get_db),
) -> MassifLeafCatalogsResponse:
    """Catalogues feuilles sous Massif Type, optionnellement filtrés par fourchette de poids."""
    try:
        return list_massif_leaf_catalogs(
            db,
            root_name=root_name,
            poids_min=poids_min,
            poids_max=poids_max,
        )
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.get("/massif/weight-bands", response_model=MassifWeightBandsResponse)
def portal_massif_weight_bands(
    root_name: str = Query("Massif Type", min_length=1),
    db: Session = Depends(get_db),
) -> MassifWeightBandsResponse:
    """Fourchettes de poids disponibles (au moins 1 produit) sous Massif Type."""
    try:
        return list_massif_available_weight_bands(db, root_name=root_name)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.post("/massif/products", response_model=MassifProductsResponse)
def portal_massif_products(
    payload: MassifProductsRequest,
    root_name: str = Query("Massif Type", min_length=1),
    db: Session = Depends(get_db),
) -> MassifProductsResponse:
    """Produits d'un catalogue feuille Massif, filtrés par poids exact ou fourchette + attributs."""
    try:
        return list_massif_products(db, payload, root_name=root_name)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.get("/massif/manilles", response_model=MassifManillesResponse)
def portal_massif_manilles(db: Session = Depends(get_db)) -> MassifManillesResponse:
    """Manilles du catalogue [Massif/Accessoire], pour matching par « Manille Type »."""
    try:
        return list_massif_manilles(db)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.get("/totem/families", response_model=TotemFamiliesResponse)
def portal_totem_families(
    offer: str = Query("Acquisition", min_length=1),
    root_name: str = Query("Totem", min_length=1),
    db: Session = Depends(get_db),
) -> TotemFamiliesResponse:
    """Familles totem sous Acquisition ou Location (prix min + description)."""
    try:
        return list_totem_families(db, offer=offer, root_name=root_name)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.get(
    "/totem/families/{family_catalog_id}/products",
    response_model=TotemProductsResponse,
)
def portal_totem_family_products(
    family_catalog_id: int,
    offer: str = Query("Acquisition", min_length=1),
    db: Session = Depends(get_db),
) -> TotemProductsResponse:
    """Produits d'une famille totem pour une offre (Acquisition / Location)."""
    try:
        return list_totem_family_products(
            db, family_catalog_id=family_catalog_id, offer=offer
        )
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.get("/totem/products/{product_id}", response_model=TotemProductDetailOut)
def portal_totem_product_detail(
    product_id: int,
    db: Session = Depends(get_db),
) -> TotemProductDetailOut:
    """Fiche détail totem (attributs, bullets Détail, clé fiche technique)."""
    try:
        return get_totem_product_detail(db, product_id)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.get("/totem/ballasts", response_model=TotemBallastsResponse)
def portal_totem_ballasts(db: Session = Depends(get_db)) -> TotemBallastsResponse:
    """Lests 25 kg du catalogue [Totem/Accessoire] (conformité vent)."""
    try:
        return list_totem_ballasts(db)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.post("/totem/wind-sheet-lookup", response_model=TotemWindSheetLookupResponse)
def portal_totem_wind_sheet_lookup(
    payload: TotemWindSheetLookupRequest,
) -> TotemWindSheetLookupResponse:
    """Écrit Région + Terrain sur Google Sheets, puis lit la valeur totem (B21→B46)."""
    try:
        return lookup_totem_wind_sheet(payload)
    except TotemWindSheetError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


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


@router.get("/cart/snapshot", response_model=CartSnapshotOut)
def portal_get_cart_snapshot(
    session: PortalSession = Depends(_session),
    db: Session = Depends(get_db),
) -> CartSnapshotOut:
    try:
        return get_cart_snapshot(db, session)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc


@router.put("/cart/snapshot", response_model=CartSnapshotOut)
def portal_put_cart_snapshot(
    payload: CartSnapshotPut,
    db: Session = Depends(get_db),
) -> CartSnapshotOut:
    try:
        session = PortalSession(user_id=payload.user_id, email=payload.email)
        return put_cart_snapshot(db, session, items=payload.items)
    except ClientPortalError as exc:
        raise _http_error(exc) from exc
