from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product, ShippingRate
from app.repositories import supplier_portal_repo as repo


def _normalize(value: str) -> str:
    return value.strip().lower()


def _department_from_zip(zip_code: str, country_code: str) -> str | None:
    z = zip_code.strip()
    if country_code.upper() == "FR" and len(z) >= 2 and z[:2].isdigit():
        return z[:2]
    return None


def _zone_matches_address(
    zone_to: str,
    *,
    zip_code: str,
    city: str,
    state: str | None,
    country_code: str,
) -> bool:
    zone = _normalize(zone_to)
    if not zone:
        return False

    dept = _department_from_zip(zip_code, country_code)
    candidates = {_normalize(zip_code), _normalize(city)}
    if state:
        candidates.add(_normalize(state))
    if dept:
        candidates.add(dept)

    for candidate in candidates:
        if not candidate:
            continue
        if candidate == zone or candidate in zone or zone in candidate:
            return True
        if dept and re.search(rf"\b{re.escape(dept)}\b", zone):
            return True
    return False


def list_active_shipping_rates(db: Session, company_tva: str) -> list[ShippingRate]:
    stmt = (
        select(ShippingRate)
        .where(
            ShippingRate.company_tva_intra_com == company_tva,
            ShippingRate.is_active.is_(True),
        )
        .order_by(ShippingRate.zone_to)
    )
    return list(db.scalars(stmt).all())


def find_matching_rate(
    db: Session,
    company_tva: str,
    *,
    zip_code: str,
    city: str,
    state: str | None,
    country_code: str,
) -> ShippingRate | None:
    for rate in list_active_shipping_rates(db, company_tva):
        if rate.zone_to and _zone_matches_address(
            rate.zone_to,
            zip_code=zip_code,
            city=city,
            state=state,
            country_code=country_code,
        ):
            return rate
    return None


def infer_stock_label(db: Session, product_id: int) -> str:
    attrs = repo.list_product_attributes(db, product_id)
    for attr in attrs:
        name = (attr.name or "").lower()
        if name in ("stock", "disponibilité", "disponibilite", "quantité", "quantite"):
            return attr.value or "Disponible"
    return "Disponible"
