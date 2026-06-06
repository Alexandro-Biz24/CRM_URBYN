from pydantic import BaseModel, Field

from app.schemas.supplier_portal import PortalSession


class ShippingRateListEntry(BaseModel):
    id: int
    carrier_name: str | None
    zone_from: str | None
    zone_to: str | None
    is_active: bool


class ShippingRateOut(BaseModel):
    id: int
    carrier_name: str
    zone_from: str
    zone_to: str
    is_active: bool
    weight_min_kg: float
    weight_max_kg: float
    volume_max_m3: float
    rate_per_kg: float
    base_rate: float
    currency: str


class ShippingRateZoneWrite(BaseModel):
    session: PortalSession
    carrier_name: str = Field(..., min_length=1)
    zone_from: str = Field(..., min_length=1)
    zone_to: str = Field(..., min_length=1)
    is_active: bool = True


class ShippingRatePricingWrite(BaseModel):
    session: PortalSession
    weight_min_kg: float = Field(..., ge=0)
    weight_max_kg: float = Field(..., ge=0)
    volume_max_m3: float = Field(..., ge=0)
    rate_per_kg: float = Field(..., ge=0)
    base_rate: float = Field(..., ge=0)
    currency: str = Field(..., min_length=3, max_length=3)


class PaymentMethodListEntry(BaseModel):
    id: int
    methode: str
    has_bank_info: bool


class PaymentMethodOut(BaseModel):
    id: int
    methode: str
    iban_number: str
    bic: str
    bank_name: str
    is_primary: bool


class PaymentMethodStep1Write(BaseModel):
    session: PortalSession
    methode: str = Field(..., min_length=1)


class PaymentMethodStep2Write(BaseModel):
    session: PortalSession
    iban_number: str = Field(..., min_length=1)
    bic: str = Field(..., min_length=1)
    bank_name: str = Field(..., min_length=1)
    is_primary: bool = False
