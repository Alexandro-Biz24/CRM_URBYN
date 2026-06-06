from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.supplier_portal import PortalSession
from app.schemas.supplier_shipping_payment import (
    PaymentMethodListEntry,
    PaymentMethodOut,
    PaymentMethodStep1Write,
    PaymentMethodStep2Write,
    ShippingRateListEntry,
    ShippingRateOut,
    ShippingRatePricingWrite,
    ShippingRateZoneWrite,
)
from app.services import supplier_shipping_payment as svc
from app.services.supplier_shipping_payment import PortalExtraError

router = APIRouter()


def _http_error(exc: PortalExtraError) -> HTTPException:
    code = exc.code
    status_code = status.HTTP_400_BAD_REQUEST
    if code in ("session_mismatch",):
        status_code = status.HTTP_401_UNAUTHORIZED
    elif code in ("role_mismatch", "no_company"):
        status_code = status.HTTP_403_FORBIDDEN
    elif code == "not_found":
        status_code = status.HTTP_404_NOT_FOUND
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": exc.message},
    )


@router.get("/shipping-rates", response_model=list[ShippingRateListEntry])
def portal_list_shipping_rates(
    user_id: int = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db),
) -> list[ShippingRateListEntry]:
    session = PortalSession(user_id=user_id, email=email)
    try:
        return svc.list_shipping_rates(db, session)
    except PortalExtraError as exc:
        raise _http_error(exc) from exc


@router.get("/shipping-rates/{rate_id}", response_model=ShippingRateOut)
def portal_get_shipping_rate(
    rate_id: int,
    user_id: int = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db),
) -> ShippingRateOut:
    session = PortalSession(user_id=user_id, email=email)
    try:
        return svc.get_shipping_rate(db, session, rate_id)
    except PortalExtraError as exc:
        raise _http_error(exc) from exc


@router.post("/shipping-rates", response_model=ShippingRateOut, status_code=status.HTTP_201_CREATED)
def portal_create_shipping_rate_zone(
    payload: ShippingRateZoneWrite,
    db: Session = Depends(get_db),
) -> ShippingRateOut:
    try:
        return svc.create_shipping_rate_zone(db, payload)
    except PortalExtraError as exc:
        raise _http_error(exc) from exc


@router.put("/shipping-rates/{rate_id}/zones", response_model=ShippingRateOut)
def portal_update_shipping_rate_zone(
    rate_id: int,
    payload: ShippingRateZoneWrite,
    db: Session = Depends(get_db),
) -> ShippingRateOut:
    try:
        return svc.update_shipping_rate_zone(db, rate_id, payload)
    except PortalExtraError as exc:
        raise _http_error(exc) from exc


@router.put("/shipping-rates/{rate_id}/pricing", response_model=ShippingRateOut)
def portal_update_shipping_rate_pricing(
    rate_id: int,
    payload: ShippingRatePricingWrite,
    db: Session = Depends(get_db),
) -> ShippingRateOut:
    try:
        return svc.update_shipping_rate_pricing(db, rate_id, payload)
    except PortalExtraError as exc:
        raise _http_error(exc) from exc


@router.get("/payment-methods", response_model=list[PaymentMethodListEntry])
def portal_list_payment_methods(
    user_id: int = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db),
) -> list[PaymentMethodListEntry]:
    session = PortalSession(user_id=user_id, email=email)
    try:
        return svc.list_payment_methods(db, session)
    except PortalExtraError as exc:
        raise _http_error(exc) from exc


@router.get("/payment-methods/{method_id}", response_model=PaymentMethodOut)
def portal_get_payment_method(
    method_id: int,
    user_id: int = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db),
) -> PaymentMethodOut:
    session = PortalSession(user_id=user_id, email=email)
    try:
        return svc.get_payment_method(db, session, method_id)
    except PortalExtraError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/payment-methods",
    response_model=PaymentMethodOut,
    status_code=status.HTTP_201_CREATED,
)
def portal_create_payment_method(
    payload: PaymentMethodStep1Write,
    db: Session = Depends(get_db),
) -> PaymentMethodOut:
    try:
        return svc.create_payment_method_step1(db, payload)
    except PortalExtraError as exc:
        raise _http_error(exc) from exc


@router.put("/payment-methods/{method_id}/methode", response_model=PaymentMethodOut)
def portal_update_payment_method_step1(
    method_id: int,
    payload: PaymentMethodStep1Write,
    db: Session = Depends(get_db),
) -> PaymentMethodOut:
    try:
        return svc.update_payment_method_step1(db, method_id, payload)
    except PortalExtraError as exc:
        raise _http_error(exc) from exc


@router.put("/payment-methods/{method_id}/bank", response_model=PaymentMethodOut)
def portal_update_payment_method_bank(
    method_id: int,
    payload: PaymentMethodStep2Write,
    db: Session = Depends(get_db),
) -> PaymentMethodOut:
    try:
        return svc.update_payment_method_bank(db, method_id, payload)
    except PortalExtraError as exc:
        raise _http_error(exc) from exc
