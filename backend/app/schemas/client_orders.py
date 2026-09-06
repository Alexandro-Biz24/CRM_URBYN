from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from app.schemas.supplier_portal import PortalSession


class DeliveryAddressSnapshot(BaseModel):
    company: str | None = None
    street: str | None = None
    street2: str | None = None
    postalCode: str | None = None
    city: str | None = None
    country: str | None = None
    specialInstructions: str | None = None


class ContactSnapshot(BaseModel):
    firstName: str = ""
    lastName: str = ""
    email: str = ""
    phone: str = ""


class ClientOrderItemIn(BaseModel):
    id: str | None = None
    type: str | None = None
    name: str
    price: float = 0
    quantity: int = 1
    details: dict[str, Any] | None = None


class ClientOrderCreate(BaseModel):
    session: PortalSession
    contact: ContactSnapshot
    deliveryAddress: DeliveryAddressSnapshot | None = None
    items: list[ClientOrderItemIn] = Field(default_factory=list)
    shippingCost: float = 0
    massifInstallFee: float = 0
    totemInstallFee: float = 0
    massifShipping: list[dict[str, Any]] | dict[str, Any] | None = None
    totalHT: float | None = None
    notes: str | None = None


class ClientOrderItemOut(BaseModel):
    id: int
    product_id: int | None = None
    item_type: str
    name: str
    quantity: int
    unit_price_ht: float
    line_total_ht: float
    line_total_ttc: float
    supplier_company_tva: str | None = None
    supplier_name: str | None = None
    details: dict[str, Any] | None = None


class ClientOrderCardOut(BaseModel):
    id: int
    status: str
    created_at: datetime
    total_ht: float
    total_ttc: float
    currency: str
    items_count: int
    suppliers: list[str] = Field(default_factory=list)
    delivery_city: str | None = None
    preview_names: list[str] = Field(default_factory=list)


class ClientOrderDetailOut(BaseModel):
    id: int
    status: str
    created_at: datetime
    updated_at: datetime
    contact_first_name: str | None = None
    contact_last_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    delivery_address: dict[str, Any] | None = None
    shipping_breakdown: Any = None
    subtotal_ht: float
    shipping_amount: float
    install_amount: float
    tax_amount: float
    total_ht: float
    total_ttc: float
    currency: str
    notes: str | None = None
    items: list[ClientOrderItemOut] = Field(default_factory=list)
    suppliers: list[str] = Field(default_factory=list)


class ClientOrderListOut(BaseModel):
    count: int
    orders: list[ClientOrderCardOut] = Field(default_factory=list)


class SupplierLeadCardOut(BaseModel):
    order_id: int
    status: str
    created_at: datetime
    buyer_label: str | None = None
    delivery_city: str | None = None
    items_count: int
    supplier_total_ht: float
    supplier_total_ttc: float
    currency: str
    preview_names: list[str] = Field(default_factory=list)


class SupplierLeadDetailOut(BaseModel):
    order_id: int
    status: str
    created_at: datetime
    buyer_label: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    delivery_address: dict[str, Any] | None = None
    currency: str
    supplier_subtotal_ht: float
    supplier_total_ht: float
    supplier_total_ttc: float
    items: list[ClientOrderItemOut] = Field(default_factory=list)


class SupplierLeadListOut(BaseModel):
    count: int
    leads: list[SupplierLeadCardOut] = Field(default_factory=list)


# ── Account settings ─────────────────────────────────────────────────────────


class AccountProfileOut(BaseModel):
    user_id: int
    email: EmailStr
    account_type: str
    title: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    mobile_phone: str | None = None
    fixe_phone: str | None = None
    company_name: str | None = None
    company_tva: str | None = None
    addresses: list[dict[str, Any]] = Field(default_factory=list)


class AccountProfileUpdate(BaseModel):
    session: PortalSession
    title: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    mobile_phone: str | None = None
    fixe_phone: str | None = None


class AccountPasswordChange(BaseModel):
    session: PortalSession
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)


class AccountEmailChangeStart(BaseModel):
    session: PortalSession
    new_email: EmailStr


class AccountEmailChangeConfirm(BaseModel):
    session: PortalSession
    code: str = Field(..., min_length=6, max_length=6)


class AccountAddressWrite(BaseModel):
    session: PortalSession
    type: str = "delivery"
    street: str | None = None
    city: str | None = None
    zip_code: str | None = None
    state: str | None = None
    country_code: str = "FR"
    is_primary: bool = False


class AccountAddressUpdate(AccountAddressWrite):
    address_id: int


class MessageOut(BaseModel):
    message: str
    expires_in_seconds: int | None = None
