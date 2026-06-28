from pydantic import BaseModel, EmailStr, Field

from app.schemas.supplier_portal import CatalogOut, MandatoryAttributeValueOut


class BuyerCatalogNavItem(BaseModel):
    id: int
    name: str | None
    has_children: bool


class BuyerProductCard(BaseModel):
    product_id: int
    product_name: str
    admin_sku: str
    image_url: str
    price: float
    currency: str
    company_name: str | None = None
    mandatory_attributes: list[MandatoryAttributeValueOut] = Field(default_factory=list)


class BuyerCatalogNavigation(BaseModel):
    catalog: CatalogOut
    children: list[BuyerCatalogNavItem] = Field(default_factory=list)
    breadcrumb: list[CatalogOut] = Field(default_factory=list)


class BuyerSearchHit(BaseModel):
    type: str = Field(..., description="catalog ou product")
    id: int
    label: str
    breadcrumb: list[str] = Field(default_factory=list)


class ProductWeightFilterRequest(BaseModel):
    catalog: list[str] = Field(..., min_length=1, description="Noms ou IDs de catalogues")
    poids_min: float = Field(..., ge=0)
    poids_max: float = Field(..., ge=0)


class ProductDimensionsOut(BaseModel):
    longueur: float | None = None
    largeur: float | None = None
    hauteur: float | None = None
    volume: float | None = None


class ProductWeightFilterItem(BaseModel):
    product_id: int
    product_name: str
    admin_sku: str
    poids: float
    dimensions: ProductDimensionsOut
    price: float
    currency: str
    company_name: str | None = None
    catalog_id: int
    catalog_name: str | None = None


class ProductWeightFilterResponse(BaseModel):
    catalog_leaf_ids: list[int] = Field(default_factory=list)
    count: int
    products: list[ProductWeightFilterItem] = Field(default_factory=list)


class ProductAttributeOut(BaseModel):
    id: int
    name: str
    value: str | None


class BuyerShippingOption(BaseModel):
    rate_id: int
    carrier_name: str
    zone_from: str
    zone_to: str
    base_rate: float
    currency: str


class BuyerProductDetail(BuyerProductCard):
    short_description: str | None = None
    description: str | None = None
    free_attributes: list[ProductAttributeOut] = Field(default_factory=list)
    stock_label: str = "Disponible"
    seller_company_tva: str
    shipping_options: list[BuyerShippingOption] = Field(default_factory=list)
    catalog_breadcrumb: list[str] = Field(default_factory=list)


class ShippingCheckRequest(BaseModel):
    user_id: int
    email: EmailStr
    product_id: int
    zip_code: str = Field(..., min_length=2)
    city: str = Field(..., min_length=1)
    state: str | None = None
    country_code: str = Field("FR", min_length=2, max_length=2)


class ShippingCheckResponse(BaseModel):
    in_delivery_zone: bool
    matched_rate_id: int | None = None
    carrier_name: str | None = None
    zone_label: str | None = None
    shipping_price: float | None = None
    currency: str | None = None
    message: str


class ShippingQuoteRequest(BaseModel):
    user_id: int
    email: EmailStr
    product_id: int
    quantity: int = Field(..., ge=1)
    delivery_street: str = Field(..., min_length=1)
    delivery_zip_code: str = Field(..., min_length=2)
    delivery_city: str = Field(..., min_length=1)
    delivery_state: str | None = None
    buyer_message: str | None = None


class CartItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    image_url: str
    seller_company_tva: str
    seller_company_name: str | None
    quantity: int
    unit_price: float
    line_total: float
    currency: str


class CartOut(BaseModel):
    cart_id: int
    status: str
    currency: str
    items: list[CartItemOut] = Field(default_factory=list)
    subtotal: float = 0
    item_count: int = 0


class CartItemAdd(BaseModel):
    user_id: int
    email: EmailStr
    product_id: int
    quantity: int = Field(..., ge=1)


class CartItemUpdate(BaseModel):
    user_id: int
    email: EmailStr
    quantity: int = Field(..., ge=1)


class CartSessionBody(BaseModel):
    user_id: int
    email: EmailStr
