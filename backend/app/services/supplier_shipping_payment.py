from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories import supplier_shipping_payment_repo as repo
from app.repositories.supplier_portal_repo import get_company_for_user, get_user
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


class PortalExtraError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _resolve_context(db: Session, session: PortalSession) -> tuple[int, str]:
    user = get_user(db, session.user_id, str(session.email))
    if user is None:
        raise PortalExtraError("session_mismatch", "Session invalide.")
    if user.role is None or user.role.role_name != "Fournisseur":
        raise PortalExtraError("role_mismatch", "Accès réservé aux fournisseurs.")
    row = get_company_for_user(db, user.id)
    if row is None:
        raise PortalExtraError("no_company", "Aucune société rattachée à ce compte.")
    return user.id, row[0]


def _shipping_out(rate) -> ShippingRateOut:
    return ShippingRateOut(
        id=rate.id,
        carrier_name=rate.carrier_name or "",
        zone_from=rate.zone_from or "",
        zone_to=rate.zone_to or "",
        is_active=rate.is_active,
        weight_min_kg=float(rate.weight_min_kg or 0),
        weight_max_kg=float(rate.weight_max_kg or 0),
        volume_max_m3=float(rate.volume_max_m3 or 0),
        rate_per_kg=float(rate.rate_per_kg or 0),
        base_rate=float(rate.base_rate or 0),
        currency=rate.currency or "EUR",
    )


def list_shipping_rates(db: Session, session: PortalSession) -> list[ShippingRateListEntry]:
    _, company_id = _resolve_context(db, session)
    return [
        ShippingRateListEntry(
            id=r.id,
            carrier_name=r.carrier_name,
            zone_from=r.zone_from,
            zone_to=r.zone_to,
            is_active=r.is_active,
        )
        for r in repo.list_shipping_rates(db, company_id)
    ]


def get_shipping_rate(db: Session, session: PortalSession, rate_id: int) -> ShippingRateOut:
    _, company_id = _resolve_context(db, session)
    rate = repo.get_shipping_rate(db, company_id, rate_id)
    if rate is None:
        raise PortalExtraError("not_found", "Tarif d'expédition introuvable.")
    return _shipping_out(rate)


def create_shipping_rate_zone(db: Session, data: ShippingRateZoneWrite) -> ShippingRateOut:
    _, company_id = _resolve_context(db, data.session)
    rate = repo.create_shipping_rate_zone(db, company_id, data)
    db.commit()
    db.refresh(rate)
    return _shipping_out(rate)


def update_shipping_rate_zone(
    db: Session, rate_id: int, data: ShippingRateZoneWrite
) -> ShippingRateOut:
    _, company_id = _resolve_context(db, data.session)
    rate = repo.get_shipping_rate(db, company_id, rate_id)
    if rate is None:
        raise PortalExtraError("not_found", "Tarif d'expédition introuvable.")
    rate = repo.update_shipping_rate_zone(db, rate, data)
    db.commit()
    db.refresh(rate)
    return _shipping_out(rate)


def update_shipping_rate_pricing(
    db: Session, rate_id: int, data: ShippingRatePricingWrite
) -> ShippingRateOut:
    _, company_id = _resolve_context(db, data.session)
    rate = repo.get_shipping_rate(db, company_id, rate_id)
    if rate is None:
        raise PortalExtraError("not_found", "Tarif d'expédition introuvable.")
    if data.weight_max_kg < data.weight_min_kg:
        raise PortalExtraError(
            "invalid_range",
            "Le poids maximum doit être supérieur ou égal au poids minimum.",
        )
    rate = repo.update_shipping_rate_pricing(db, rate, data)
    db.commit()
    db.refresh(rate)
    return _shipping_out(rate)


def list_payment_methods(db: Session, session: PortalSession) -> list[PaymentMethodListEntry]:
    user_id, company_id = _resolve_context(db, session)
    return [
        PaymentMethodListEntry(
            id=pm.id,
            methode=pm.methode,
            has_bank_info=repo.get_bank_info_for_payment_method(db, pm.id) is not None,
        )
        for pm in repo.list_payment_methods(db, company_id, user_id)
    ]


def get_payment_method(
    db: Session, session: PortalSession, method_id: int
) -> PaymentMethodOut:
    user_id, company_id = _resolve_context(db, session)
    pm = repo.get_payment_method(db, company_id, user_id, method_id)
    if pm is None:
        raise PortalExtraError("not_found", "Méthode de paiement introuvable.")
    bank = repo.get_bank_info_for_payment_method(db, pm.id)
    return PaymentMethodOut(
        id=pm.id,
        methode=pm.methode,
        iban_number=bank.iban_number if bank and bank.iban_number else "",
        bic=bank.bic if bank and bank.bic else "",
        bank_name=bank.bank_name if bank and bank.bank_name else "",
        is_primary=bank.is_primary if bank else False,
    )


def create_payment_method_step1(db: Session, data: PaymentMethodStep1Write) -> PaymentMethodOut:
    user_id, company_id = _resolve_context(db, data.session)
    pm = repo.create_payment_method_step1(db, company_id, user_id, data)
    db.commit()
    db.refresh(pm)
    return PaymentMethodOut(
        id=pm.id,
        methode=pm.methode,
        iban_number="",
        bic="",
        bank_name="",
        is_primary=False,
    )


def update_payment_method_step1(
    db: Session, method_id: int, data: PaymentMethodStep1Write
) -> PaymentMethodOut:
    user_id, company_id = _resolve_context(db, data.session)
    pm = repo.get_payment_method(db, company_id, user_id, method_id)
    if pm is None:
        raise PortalExtraError("not_found", "Méthode de paiement introuvable.")
    pm = repo.update_payment_method_step1(db, pm, data)
    db.commit()
    db.refresh(pm)
    existing = get_payment_method(db, data.session, method_id)
    return existing


def update_payment_method_bank(
    db: Session, method_id: int, data: PaymentMethodStep2Write
) -> PaymentMethodOut:
    user_id, company_id = _resolve_context(db, data.session)
    pm = repo.get_payment_method(db, company_id, user_id, method_id)
    if pm is None:
        raise PortalExtraError("not_found", "Méthode de paiement introuvable.")
    repo.upsert_payment_method_bank(db, company_id, pm, data)
    db.commit()
    return get_payment_method(db, data.session, method_id)
