from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.admin_deps import require_admin
from app.core.deps import get_db
from app.schemas.admin import (
    AdminCatalogDetail,
    AdminCatalogTreeResponse,
    AdminCatalogUpdate,
    AdminCatalogWrite,
    AdminLoginRequest,
    AdminLoginResponse,
)
from app.services import admin as admin_svc
from app.services.admin import AdminError

router = APIRouter()


def _http_error(exc: AdminError) -> HTTPException:
    status_code = status.HTTP_400_BAD_REQUEST
    if exc.code in ("invalid_credentials", "admin_unauthorized"):
        status_code = status.HTTP_401_UNAUTHORIZED
    elif exc.code == "not_found":
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code in ("has_children", "has_orders"):
        status_code = status.HTTP_409_CONFLICT
    elif exc.code == "admin_not_configured":
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.message},
    )


@router.post("/login", response_model=AdminLoginResponse)
def admin_login(body: AdminLoginRequest) -> AdminLoginResponse:
    try:
        return admin_svc.login(body.login, body.password)
    except AdminError as exc:
        raise _http_error(exc) from exc


@router.get("/catalogs/tree", response_model=AdminCatalogTreeResponse)
def admin_catalog_tree(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> AdminCatalogTreeResponse:
    return admin_svc.get_catalog_tree(db)


@router.get("/catalogs/{catalog_id}", response_model=AdminCatalogDetail)
def admin_get_catalog(
    catalog_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> AdminCatalogDetail:
    try:
        return admin_svc.get_catalog_detail(db, catalog_id)
    except AdminError as exc:
        raise _http_error(exc) from exc


@router.post("/catalogs", response_model=AdminCatalogDetail, status_code=status.HTTP_201_CREATED)
def admin_create_catalog(
    body: AdminCatalogWrite,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> AdminCatalogDetail:
    try:
        return admin_svc.create_catalog(db, body)
    except AdminError as exc:
        raise _http_error(exc) from exc


@router.put("/catalogs/{catalog_id}", response_model=AdminCatalogDetail)
def admin_update_catalog(
    catalog_id: int,
    body: AdminCatalogUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> AdminCatalogDetail:
    try:
        return admin_svc.update_catalog(db, catalog_id, body)
    except AdminError as exc:
        raise _http_error(exc) from exc


@router.delete("/catalogs/{catalog_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_catalog(
    catalog_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> None:
    try:
        admin_svc.delete_catalog(db, catalog_id)
    except AdminError as exc:
        raise _http_error(exc) from exc
