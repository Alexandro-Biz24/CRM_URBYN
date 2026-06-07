from pydantic import BaseModel, Field


class ShippingRateCreateV2(BaseModel):
    company_id: str | None = None
    user_id: int | None = None
    carrier_name: str | None = None
    zone_from: str | None = None
    zone_to: str | None = None
    weight_min_kg: float | None = None
    weight_max_kg: float | None = None
    volume_max_m3: float | None = None
    rate_per_kg: float | None = None
    base_rate: float | None = None
    currency: str | None = None
    is_active: bool = True


class CatalogCreateV2(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool = True
    parent_id: int | None = None


class MandatoryAttributeValueCreateV2(BaseModel):
    definition_id: int
    value: str = Field(..., min_length=1)


class ProductCreateV2(BaseModel):
    primary_catalog_id: int
    additional_catalog_ids: list[int] = Field(default_factory=list)
    client_sku: str
    product_name: str
    price: float = Field(..., ge=0)
    currency: str = "EUR"
    is_active: bool = True
    mandatory_attributes: list[MandatoryAttributeValueCreateV2] = Field(default_factory=list)


class SupplierOfferCreateV2(BaseModel):
    company_id: str | None = None
    user_id: int | None = None
    catalog: CatalogCreateV2 | None = None
    primary_catalog_id: int | None = None
    product: ProductCreateV2


class ProductUpdateV2(BaseModel):
    primary_catalog_id: int | None = None
    additional_catalog_ids: list[int] | None = None
    client_sku: str | None = None
    product_name: str | None = None
    price: float | None = Field(None, ge=0)
    currency: str | None = None
    is_active: bool | None = None
    mandatory_attributes: list[MandatoryAttributeValueCreateV2] | None = None


class ShippingRateCreatedV2(BaseModel):
    id: int
    company_id: str


class SupplierOfferCreatedV2(BaseModel):
    catalog_id: int
    product_id: int
    admin_sku: str
    company_id: str


class ProductUpdatedV2(BaseModel):
    company_id: str
    product_id: int
    updated_fields: list[str] = Field(default_factory=list)
