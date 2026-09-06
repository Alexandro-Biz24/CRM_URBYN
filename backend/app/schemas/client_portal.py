from datetime import datetime
from typing import Any

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
    profondeur: float | None = None
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


# ── Massif (racine « Massif Type ») ───────────────────────────────────────────

MASSIF_ROOT_DEFAULT = "Massif Type"


class MassifLeafCatalogOut(BaseModel):
    id: int
    name: str | None
    description: str | None = None
    parent_id: int | None = None
    breadcrumb: list[str] = Field(default_factory=list)


class MassifLeafCatalogsResponse(BaseModel):
    root_id: int
    root_name: str
    count: int
    catalogs: list[MassifLeafCatalogOut] = Field(default_factory=list)


class MassifWeightBandOut(BaseModel):
    poids_min: float
    poids_max: float
    product_count: int = 0
    available: bool = False


class MassifWeightBandsResponse(BaseModel):
    root_id: int
    root_name: str
    bands: list[MassifWeightBandOut] = Field(default_factory=list)


class MassifProductsRequest(BaseModel):
    catalog_id: int = Field(
        ...,
        ge=1,
        description="Catalogue feuille sous « Massif Type »",
    )
    poids: float | None = Field(
        default=None,
        ge=0,
        description="Poids exact (kg). Si fourni, remplace poids_min/poids_max.",
    )
    poids_min: float | None = Field(default=None, ge=0)
    poids_max: float | None = Field(default=None, ge=0)


class MassifProductOut(BaseModel):
    product_id: int
    product_name: str
    admin_sku: str
    description: str | None = None
    poids: float
    dimensions: ProductDimensionsOut
    price: float
    currency: str
    company_name: str | None = None
    company_tva: str | None = None
    company_zip: str | None = None
    company_city: str | None = None
    company_country: str | None = None
    catalog_id: int
    catalog_name: str | None = None
    mandatory_attributes: list[MandatoryAttributeValueOut] = Field(default_factory=list)
    free_attributes: list[ProductAttributeOut] = Field(default_factory=list)


class MassifProductsResponse(BaseModel):
    catalog_id: int
    catalog_name: str | None = None
    poids_min: float
    poids_max: float
    count: int
    products: list[MassifProductOut] = Field(default_factory=list)


class MassifManilleOut(BaseModel):
    product_id: int
    product_name: str
    admin_sku: str
    description: str | None = None
    manille_type: str
    price: float
    currency: str = "EUR"
    company_name: str | None = None
    company_tva: str | None = None
    poids: float | None = None


class MassifManillesResponse(BaseModel):
    catalog_id: int
    catalog_path: list[str] = Field(default_factory=list)
    count: int
    manilles: list[MassifManilleOut] = Field(default_factory=list)


class TotemBallastOut(BaseModel):
    """Lest 25 kg du catalogue [Totem/Accessoire]."""

    product_id: int
    product_name: str
    client_sku: str | None = None
    admin_sku: str | None = None
    description: str | None = None
    price: float
    currency: str = "EUR"
    poids: float | None = None
    company_name: str | None = None
    company_tva: str | None = None


class TotemBallastsResponse(BaseModel):
    catalog_id: int
    catalog_path: list[str] = Field(default_factory=list)
    count: int
    ballasts: list[TotemBallastOut] = Field(default_factory=list)
    # Produit lest 25 kg privilégié pour le front conformité vent
    default_ballast: TotemBallastOut | None = None


# ── Totem (racine « Totem », feuilles Acquisition / Location) ─────────────────

TOTEM_ROOT_DEFAULT = "Totem"


class TotemFamilyOut(BaseModel):
    family_catalog_id: int
    leaf_catalog_id: int
    name: str
    display_name: str
    description: str | None = None
    min_price: float
    currency: str = "EUR"
    product_count: int = 0
    min_dimensions_label: str | None = None
    breadcrumb: list[str] = Field(default_factory=list)


class TotemFamiliesResponse(BaseModel):
    root_id: int
    root_name: str
    offer: str
    count: int
    families: list[TotemFamilyOut] = Field(default_factory=list)


class TotemProductOut(BaseModel):
    product_id: int
    product_name: str
    client_sku: str | None = None
    price: float
    currency: str = "EUR"
    dimensions_label: str | None = None
    dimensions: ProductDimensionsOut = Field(default_factory=ProductDimensionsOut)
    poids: float | None = None
    attributes: dict[str, str] = Field(default_factory=dict)


class TotemProductsResponse(BaseModel):
    family_catalog_id: int
    leaf_catalog_id: int
    family_name: str
    offer: str
    count: int
    products: list[TotemProductOut] = Field(default_factory=list)


class TotemProductDetailOut(BaseModel):
    product_id: int
    product_name: str
    client_sku: str | None = None
    price: float
    currency: str = "EUR"
    description: str | None = None
    dimensions_label: str | None = None
    dimensions: ProductDimensionsOut = Field(default_factory=ProductDimensionsOut)
    poids: float | None = None
    footprint: str | None = None
    panel_format: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    detail_bullets: list[str] = Field(default_factory=list)
    fiche_document_key: str | None = None
    fiche_available: bool = False
    company_name: str | None = None
    company_tva: str | None = None


class TotemWindSheetProductIn(BaseModel):
    cart_item_id: str | None = None
    product_id: int | None = None
    product_name: str | None = None
    client_sku: str | None = None
    format: str | None = None


class TotemWindSheetLookupRequest(BaseModel):
    """Région (zone vent) + terrain UI → écriture Sheets + lookup valeurs totems."""

    wind_zone: int = Field(..., ge=1, le=4, description="Zone de vent 1..4 → Région N")
    terrain: str = Field(
        ...,
        min_length=1,
        description="Clé UI (bord_mer, …) ou label sheet exact",
    )
    products: list[TotemWindSheetProductIn] = Field(default_factory=list)


class TotemWindSheetProductOut(BaseModel):
    cart_item_id: str | None = None
    product_id: int | None = None
    product_name: str | None = None
    sheet_header: str | None = None
    supported: bool
    matched: bool = False
    value: Any = None
    message: str | None = None


class TotemWindSheetLookupResponse(BaseModel):
    region_sheet: str
    terrain_sheet: str
    write_ok: bool
    settle_ms: int
    products: list[TotemWindSheetProductOut] = Field(default_factory=list)


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


class CartSnapshotOut(BaseModel):
    cart_id: int
    items: list[dict] = Field(default_factory=list)
    updated_at: datetime | None = None


class CartSnapshotPut(BaseModel):
    user_id: int
    email: EmailStr
    items: list[dict] = Field(default_factory=list)
