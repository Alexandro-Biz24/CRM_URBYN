from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.client_orders import (
    AccountAddressUpdate,
    AccountAddressWrite,
    AccountEmailChangeConfirm,
    AccountEmailChangeStart,
    AccountPasswordChange,
    AccountProfileOut,
    AccountProfileUpdate,
    ClientOrderCreate,
    ClientOrderDetailOut,
    ClientOrderListOut,
    MessageOut,
    SupplierLeadDetailOut,
    SupplierLeadListOut,
)
from app.schemas.supplier_portal import PortalSession
from app.services import account_settings as account_svc
from app.services import client_orders as orders_svc
from app.services.account_settings import AccountSettingsError
from app.services.client_portal import ClientPortalError
from app.services.supplier_portal import PortalError as SupplierPortalError

router = APIRouter()


def _client_http(exc: ClientPortalError | AccountSettingsError) -> HTTPException:
    code = exc.code
    status_code = status.HTTP_400_BAD_REQUEST
    if code in ("session_mismatch", "invalid_credentials"):
        status_code = status.HTTP_401_UNAUTHORIZED
    elif code in ("role_mismatch", "no_company"):
        status_code = status.HTTP_403_FORBIDDEN
    elif code in ("not_found",):
        status_code = status.HTTP_404_NOT_FOUND
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": exc.message},
    )


def _supplier_http(exc: SupplierPortalError | AccountSettingsError) -> HTTPException:
    return _client_http(exc)  # type: ignore[arg-type]


# ── Client orders (Commandes) ────────────────────────────────────────────────


@router.post("/client-portal/orders", response_model=ClientOrderDetailOut)
def create_order(payload: ClientOrderCreate, db: Session = Depends(get_db)):
    try:
        return orders_svc.create_client_order(db, payload)
    except ClientPortalError as exc:
        raise _client_http(exc) from exc


@router.get("/client-portal/orders", response_model=ClientOrderListOut)
def list_orders(
    user_id: int = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        return orders_svc.list_buyer_orders(
            db, PortalSession(user_id=user_id, email=email)
        )
    except ClientPortalError as exc:
        raise _client_http(exc) from exc


@router.get("/client-portal/orders/{order_id}", response_model=ClientOrderDetailOut)
def get_order(
    order_id: int,
    user_id: int = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        return orders_svc.get_buyer_order_detail(
            db, PortalSession(user_id=user_id, email=email), order_id
        )
    except ClientPortalError as exc:
        raise _client_http(exc) from exc


# ── Supplier leads ───────────────────────────────────────────────────────────


@router.get("/supplier-portal/leads", response_model=SupplierLeadListOut)
def list_leads(
    user_id: int = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        return orders_svc.list_supplier_leads(
            db, PortalSession(user_id=user_id, email=email)
        )
    except SupplierPortalError as exc:
        raise _supplier_http(exc) from exc


@router.get("/supplier-portal/leads/{order_id}", response_model=SupplierLeadDetailOut)
def get_lead(
    order_id: int,
    user_id: int = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        return orders_svc.get_supplier_lead_detail(
            db, PortalSession(user_id=user_id, email=email), order_id
        )
    except SupplierPortalError as exc:
        raise _supplier_http(exc) from exc


# ── Account settings (client + fournisseur) ──────────────────────────────────


@router.get("/account/profile", response_model=AccountProfileOut)
def account_profile(
    user_id: int = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        return account_svc.get_account_profile(
            db, PortalSession(user_id=user_id, email=email)
        )
    except AccountSettingsError as exc:
        raise _client_http(exc) from exc


@router.put("/account/profile", response_model=AccountProfileOut)
def account_profile_update(payload: AccountProfileUpdate, db: Session = Depends(get_db)):
    try:
        return account_svc.update_account_profile(db, payload)
    except AccountSettingsError as exc:
        raise _client_http(exc) from exc


@router.post("/account/password", response_model=MessageOut)
def account_password(payload: AccountPasswordChange, db: Session = Depends(get_db)):
    try:
        return account_svc.change_password(db, payload)
    except AccountSettingsError as exc:
        raise _client_http(exc) from exc


@router.post("/account/email/start", response_model=MessageOut)
def account_email_start(payload: AccountEmailChangeStart, db: Session = Depends(get_db)):
    try:
        return account_svc.start_email_change(db, payload)
    except AccountSettingsError as exc:
        raise _client_http(exc) from exc
    except Exception as exc:
        # SignupError from email delivery
        from app.services.signup import SignupError

        if isinstance(exc, SignupError):
            raise _client_http(AccountSettingsError(exc.code, exc.message)) from exc
        raise


@router.post("/account/email/confirm", response_model=AccountProfileOut)
def account_email_confirm(
    payload: AccountEmailChangeConfirm, db: Session = Depends(get_db)
):
    try:
        return account_svc.confirm_email_change(db, payload)
    except AccountSettingsError as exc:
        raise _client_http(exc) from exc


@router.post("/account/addresses", response_model=AccountProfileOut)
def account_address_add(payload: AccountAddressWrite, db: Session = Depends(get_db)):
    try:
        return account_svc.add_address(db, payload)
    except AccountSettingsError as exc:
        raise _client_http(exc) from exc


@router.put("/account/addresses", response_model=AccountProfileOut)
def account_address_update(
    payload: AccountAddressUpdate, db: Session = Depends(get_db)
):
    try:
        return account_svc.update_address(db, payload)
    except AccountSettingsError as exc:
        raise _client_http(exc) from exc


@router.delete("/account/addresses/{address_id}", response_model=AccountProfileOut)
def account_address_delete(
    address_id: int,
    user_id: int = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        return account_svc.delete_address(
            db, PortalSession(user_id=user_id, email=email), address_id
        )
    except AccountSettingsError as exc:
        raise _client_http(exc) from exc
