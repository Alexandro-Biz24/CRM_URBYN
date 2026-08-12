from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.admin_deps import require_admin
from app.core.deps import get_db
from app.schemas.admin import (
    AdminCatalogDetail,
    AdminCatalogProductEntry,
    AdminCatalogTreeResponse,
    AdminCatalogUpdate,
    AdminCatalogWrite,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminProductDetail,
    CatalogAttributeMandatoryUpdate,
    CatalogCsvImportMode,
    CatalogCsvImportResult,
    CatalogProductAttributeOut,
)
from app.services import admin as admin_svc
from app.services import catalog_csv_import as csv_import_svc
from app.services.admin import AdminError

router = APIRouter()


def _accounts_http_error(exc) -> HTTPException:
    from app.services.admin_accounts import AdminAccountsError

    if not isinstance(exc, AdminAccountsError):
        raise exc
    status_code = status.HTTP_400_BAD_REQUEST
    if exc.code == "not_found":
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code == "has_orders":
        status_code = status.HTTP_409_CONFLICT
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.message},
    )


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
    elif exc.code == "company_not_found":
        status_code = status.HTTP_404_NOT_FOUND
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


@router.post(
    "/catalogs/import-csv",
    response_model=CatalogCsvImportResult,
)
async def admin_import_catalog_csv(
    file: UploadFile = File(...),
    mode: CatalogCsvImportMode = Form(CatalogCsvImportMode.additive),
    company_tva_intra_com: str = Form(""),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> CatalogCsvImportResult:
    raw = await file.read()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "empty_file", "message": "Fichier vide."},
        )
    try:
        return csv_import_svc.import_catalog_csv(
            db,
            content=raw,
            mode=mode,
            company_tva_intra_com=company_tva_intra_com or None,
        )
    except AdminError as exc:
        db.rollback()
        raise _http_error(exc) from exc
    except Exception:
        db.rollback()
        raise


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


@router.get(
    "/catalogs/{catalog_id}/products",
    response_model=list[AdminCatalogProductEntry],
)
def admin_list_catalog_products(
    catalog_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> list[AdminCatalogProductEntry]:
    try:
        return admin_svc.list_catalog_products(db, catalog_id)
    except AdminError as exc:
        raise _http_error(exc) from exc


@router.get(
    "/catalogs/{catalog_id}/product-attributes",
    response_model=list[CatalogProductAttributeOut],
)
def admin_list_catalog_product_attributes(
    catalog_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> list[CatalogProductAttributeOut]:
    try:
        return admin_svc.list_catalog_product_attributes(db, catalog_id)
    except AdminError as exc:
        raise _http_error(exc) from exc


@router.put(
    "/catalogs/{catalog_id}/product-attributes/{attribute_name}/mandatory",
    response_model=CatalogProductAttributeOut,
)
def admin_set_catalog_attribute_mandatory(
    catalog_id: int,
    attribute_name: str,
    body: CatalogAttributeMandatoryUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> CatalogProductAttributeOut:
    try:
        return admin_svc.set_catalog_attribute_mandatory(
            db, catalog_id, attribute_name, body
        )
    except AdminError as exc:
        raise _http_error(exc) from exc


@router.get("/products/{product_id}", response_model=AdminProductDetail)
def admin_get_product(
    product_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> AdminProductDetail:
    try:
        return admin_svc.get_product_detail(db, product_id)
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


@router.get("/users")
def admin_list_users(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    from app.services import admin_accounts as accounts_svc

    return accounts_svc.list_users(db)


@router.get("/users/{user_id}")
def admin_get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    from app.services import admin_accounts as accounts_svc

    try:
        return accounts_svc.get_user(db, user_id)
    except Exception as exc:
        raise _accounts_http_error(exc) from exc


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> None:
    from app.services import admin_accounts as accounts_svc

    try:
        accounts_svc.delete_user(db, user_id)
    except Exception as exc:
        raise _accounts_http_error(exc) from exc


@router.get("/companies")
def admin_list_companies(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    from app.services import admin_accounts as accounts_svc

    return accounts_svc.list_companies(db)


@router.get("/companies/{tva_intra_com}")
def admin_get_company(
    tva_intra_com: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    from app.services import admin_accounts as accounts_svc

    try:
        return accounts_svc.get_company(db, tva_intra_com)
    except Exception as exc:
        raise _accounts_http_error(exc) from exc


@router.delete("/companies/{tva_intra_com}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_company(
    tva_intra_com: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> None:
    from app.services import admin_accounts as accounts_svc

    try:
        accounts_svc.delete_company(db, tva_intra_com)
    except Exception as exc:
        raise _accounts_http_error(exc) from exc
