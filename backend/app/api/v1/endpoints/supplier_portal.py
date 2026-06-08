from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.supplier_portal import (
    CatalogAttributeDefinitionOut,
    CatalogOut,
    PortalContext,
    PortalSession,
    ProductAttributOut,
    ProductAttributUpdateBody,
    ProductAttributWrite,
    ProductCatalogGroupsResponse,
    ProductListEntry,
    ProductOut,
    ProductWrite,
)
from app.services import supplier_portal as portal_svc
from app.services.supplier_portal import PortalError

router = APIRouter()


def _http_error(exc: PortalError) -> HTTPException:
    code = exc.code
    status_code = status.HTTP_400_BAD_REQUEST
    if code in ("session_mismatch", "invalid_credentials"):
        status_code = status.HTTP_401_UNAUTHORIZED
    elif code in ("role_mismatch",):
        status_code = status.HTTP_403_FORBIDDEN
    elif code in ("not_found", "parent_not_found"):
        status_code = status.HTTP_404_NOT_FOUND
    elif code in ("no_company",):
        status_code = status.HTTP_403_FORBIDDEN
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": exc.message},
    )


@router.post("/context", response_model=PortalContext)
def portal_context(payload: PortalSession, db: Session = Depends(get_db)) -> PortalContext:
    try:
        return portal_svc.get_context(db, payload)
    except PortalError as exc:
        raise _http_error(exc) from exc


@router.get("/catalogs/roots", response_model=list[CatalogOut])
def portal_list_root_catalogs(
    user_id: int = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db),
) -> list[CatalogOut]:
    session = PortalSession(user_id=user_id, email=email)
    try:
        return portal_svc.list_root_catalogs(db, session)
    except PortalError as exc:
        raise _http_error(exc) from exc


@router.get("/catalogs/search", response_model=list[CatalogOut])
def portal_search_catalogs(
    user_id: int = Query(...),
    email: str = Query(...),
    q: str = Query(..., min_length=1),
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[CatalogOut]:
    session = PortalSession(user_id=user_id, email=email)
    try:
        return portal_svc.search_catalogs(db, session, q, limit)
    except PortalError as exc:
        raise _http_error(exc) from exc


@router.get("/catalogs/{catalog_id}/children", response_model=list[CatalogOut])
def portal_list_catalog_children(
    catalog_id: int,
    user_id: int = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db),
) -> list[CatalogOut]:
    session = PortalSession(user_id=user_id, email=email)
    try:
        return portal_svc.list_catalog_children(db, session, catalog_id)
    except PortalError as exc:
        raise _http_error(exc) from exc


@router.get("/catalogs", response_model=list[CatalogOut])
def portal_list_catalogs(
    user_id: int = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db),
) -> list[CatalogOut]:
    session = PortalSession(user_id=user_id, email=email)
    try:
        return portal_svc.list_catalogs(db, session)
    except PortalError as exc:
        raise _http_error(exc) from exc


@router.get("/catalogs/{catalog_id}", response_model=CatalogOut)
def portal_get_catalog(
    catalog_id: int,
    user_id: int = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db),
) -> CatalogOut:
    session = PortalSession(user_id=user_id, email=email)
    try:
        return portal_svc.get_catalog(db, session, catalog_id)
    except PortalError as exc:
        raise _http_error(exc) from exc


@router.get(
    "/catalogs/{catalog_id}/attribute-definitions",
    response_model=list[CatalogAttributeDefinitionOut],
)
def portal_list_catalog_attribute_definitions(
    catalog_id: int,
    user_id: int = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db),
) -> list[CatalogAttributeDefinitionOut]:
    session = PortalSession(user_id=user_id, email=email)
    try:
        return portal_svc.list_catalog_attribute_definitions(db, session, catalog_id)
    except PortalError as exc:
        raise _http_error(exc) from exc


@router.get("/products/grouped-by-catalog", response_model=ProductCatalogGroupsResponse)
def portal_list_products_grouped(
    user_id: int = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db),
) -> ProductCatalogGroupsResponse:
    session = PortalSession(user_id=user_id, email=email)
    try:
        return portal_svc.list_products_grouped(db, session)
    except PortalError as exc:
        raise _http_error(exc) from exc


@router.get("/products", response_model=list[ProductListEntry])
def portal_list_products(
    user_id: int = Query(...),
    email: str = Query(...),
    catalog_id: int | None = Query(None),
    db: Session = Depends(get_db),
) -> list[ProductListEntry]:
    session = PortalSession(user_id=user_id, email=email)
    try:
        return portal_svc.list_products(db, session, catalog_id)
    except PortalError as exc:
        raise _http_error(exc) from exc


@router.get("/products/{product_id}", response_model=ProductOut)
def portal_get_product(
    product_id: int,
    user_id: int = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db),
) -> ProductOut:
    session = PortalSession(user_id=user_id, email=email)
    try:
        return portal_svc.get_product(db, session, product_id)
    except PortalError as exc:
        raise _http_error(exc) from exc


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def portal_create_product(
    body: ProductWrite,
    db: Session = Depends(get_db),
) -> ProductOut:
    try:
        return portal_svc.create_product(db, body)
    except PortalError as exc:
        raise _http_error(exc) from exc


@router.put("/products/{product_id}", response_model=ProductOut)
def portal_update_product(
    product_id: int,
    body: ProductWrite,
    db: Session = Depends(get_db),
) -> ProductOut:
    try:
        return portal_svc.update_product(db, product_id, body)
    except PortalError as exc:
        raise _http_error(exc) from exc


@router.get("/products/{product_id}/attributes", response_model=list[ProductAttributOut])
def portal_list_attributes(
    product_id: int,
    user_id: int = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db),
) -> list[ProductAttributOut]:
    session = PortalSession(user_id=user_id, email=email)
    try:
        return portal_svc.list_attributes(db, session, product_id)
    except PortalError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/products/{product_id}/attributes",
    response_model=ProductAttributOut,
    status_code=status.HTTP_201_CREATED,
)
def portal_add_attribute(
    product_id: int,
    body: ProductAttributWrite,
    db: Session = Depends(get_db),
) -> ProductAttributOut:
    try:
        return portal_svc.add_attribute(db, product_id, body)
    except PortalError as exc:
        raise _http_error(exc) from exc


@router.put(
    "/products/{product_id}/attributes/{attr_id}",
    response_model=ProductAttributOut,
)
def portal_update_attribute(
    product_id: int,
    attr_id: int,
    body: ProductAttributUpdateBody,
    db: Session = Depends(get_db),
) -> ProductAttributOut:
    try:
        return portal_svc.update_attribute(db, product_id, attr_id, body)
    except PortalError as exc:
        raise _http_error(exc) from exc


@router.delete(
    "/products/{product_id}/attributes/{attr_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def portal_delete_attribute(
    product_id: int,
    attr_id: int,
    user_id: int = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db),
) -> None:
    session = PortalSession(user_id=user_id, email=email)
    try:
        portal_svc.delete_attribute(db, session, product_id, attr_id)
    except PortalError as exc:
        raise _http_error(exc) from exc
