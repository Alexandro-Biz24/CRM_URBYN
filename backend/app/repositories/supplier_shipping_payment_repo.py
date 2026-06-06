from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CompanyBankInfo, CompanyPaymentMethod, ShippingRate
from app.schemas.supplier_shipping_payment import (
    PaymentMethodStep1Write,
    PaymentMethodStep2Write,
    ShippingRatePricingWrite,
    ShippingRateZoneWrite,
)


def list_shipping_rates(db: Session, company_id: str) -> list[ShippingRate]:
    stmt = (
        select(ShippingRate)
        .where(ShippingRate.company_tva_intra_com == company_id)
        .order_by(ShippingRate.updated_at.desc())
    )
    return list(db.scalars(stmt).all())


def get_shipping_rate(db: Session, company_id: str, rate_id: int) -> ShippingRate | None:
    return db.scalar(
        select(ShippingRate).where(
            ShippingRate.id == rate_id,
            ShippingRate.company_tva_intra_com == company_id,
        )
    )


def create_shipping_rate_zone(
    db: Session, company_id: str, data: ShippingRateZoneWrite
) -> ShippingRate:
    rate = ShippingRate(
        company_tva_intra_com=company_id,
        carrier_name=data.carrier_name.strip(),
        zone_from=data.zone_from.strip(),
        zone_to=data.zone_to.strip(),
        is_active=data.is_active,
        weight_min_kg=0.0,
        weight_max_kg=0.0,
        volume_max_m3=0.0,
        rate_per_kg=Decimal("0"),
        base_rate=Decimal("0"),
        currency="EUR",
    )
    db.add(rate)
    db.flush()
    return rate


def update_shipping_rate_zone(
    db: Session, rate: ShippingRate, data: ShippingRateZoneWrite
) -> ShippingRate:
    rate.carrier_name = data.carrier_name.strip()
    rate.zone_from = data.zone_from.strip()
    rate.zone_to = data.zone_to.strip()
    rate.is_active = data.is_active
    rate.updated_at = datetime.utcnow()
    db.flush()
    return rate


def update_shipping_rate_pricing(
    db: Session, rate: ShippingRate, data: ShippingRatePricingWrite
) -> ShippingRate:
    rate.weight_min_kg = data.weight_min_kg
    rate.weight_max_kg = data.weight_max_kg
    rate.volume_max_m3 = data.volume_max_m3
    rate.rate_per_kg = Decimal(str(data.rate_per_kg))
    rate.base_rate = Decimal(str(data.base_rate))
    rate.currency = data.currency.upper()[:3]
    rate.updated_at = datetime.utcnow()
    db.flush()
    return rate


def list_payment_methods(db: Session, company_id: str, user_id: int) -> list[CompanyPaymentMethod]:
    stmt = (
        select(CompanyPaymentMethod)
        .where(
            CompanyPaymentMethod.company_tva_intra_com == company_id,
            CompanyPaymentMethod.user_id == user_id,
        )
        .order_by(CompanyPaymentMethod.id.desc())
    )
    return list(db.scalars(stmt).all())


def get_payment_method(
    db: Session, company_id: str, user_id: int, method_id: int
) -> CompanyPaymentMethod | None:
    return db.scalar(
        select(CompanyPaymentMethod)
        .where(
            CompanyPaymentMethod.id == method_id,
            CompanyPaymentMethod.company_tva_intra_com == company_id,
            CompanyPaymentMethod.user_id == user_id,
        )
    )


def get_bank_info(db: Session, bank_info_id: int) -> CompanyBankInfo | None:
    return db.scalar(select(CompanyBankInfo).where(CompanyBankInfo.id == bank_info_id))


def get_bank_info_for_payment_method(
    db: Session, payment_method_id: int
) -> CompanyBankInfo | None:
    return db.scalar(
        select(CompanyBankInfo).where(
            CompanyBankInfo.company_payment_method_id == payment_method_id
        )
    )


def create_payment_method_step1(
    db: Session, company_id: str, user_id: int, data: PaymentMethodStep1Write
) -> CompanyPaymentMethod:
    pm = CompanyPaymentMethod(
        methode=data.methode.strip(),
        user_id=user_id,
        company_tva_intra_com=company_id,
    )
    db.add(pm)
    db.flush()
    return pm


def update_payment_method_step1(
    db: Session, pm: CompanyPaymentMethod, data: PaymentMethodStep1Write
) -> CompanyPaymentMethod:
    pm.methode = data.methode.strip()
    db.flush()
    return pm


def upsert_payment_method_bank(
    db: Session,
    company_id: str,
    pm: CompanyPaymentMethod,
    data: PaymentMethodStep2Write,
) -> CompanyBankInfo:
    bank = get_bank_info_for_payment_method(db, pm.id)

    if bank is None:
        bank = CompanyBankInfo(
            company_tva_intra_com=company_id,
            iban_number=data.iban_number.strip(),
            bic=data.bic.strip().upper(),
            bank_name=data.bank_name.strip(),
            is_primary=data.is_primary,
            company_payment_method_id=pm.id,
        )
        db.add(bank)
        db.flush()
    else:
        bank.iban_number = data.iban_number.strip()
        bank.bic = data.bic.strip().upper()
        bank.bank_name = data.bank_name.strip()
        bank.is_primary = data.is_primary
        bank.company_payment_method_id = pm.id
        db.flush()

    return bank
