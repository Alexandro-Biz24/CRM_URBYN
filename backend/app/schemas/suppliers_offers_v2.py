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


class ProductCreateV2(BaseModel):
    catalog_ref: int
    client_sku: str
    product_type: str
    price: float = Field(..., ge=0)
    currency: str = "EUR"
    quantity: int = Field(0, ge=0)
    is_active: bool = True
    teinte: str | None = None
    type_de_produit: str | None = None
    gamme: str | None = None
    duree_garantie: str | None = None
    conditions_garantie: str | None = None
    piece_ouvrage_destination: str | None = None
    traitement_bois_classification: str | None = None
    produit_nuance: str | None = None
    description_profil: str | None = None
    couleur_traitement_autoclave: str | None = None
    code_douane_sh8: str | None = None
    type_bois: str | None = None
    essence_bois: str | None = None
    longueur: float | None = None
    largeur: float | None = None
    hauteur: float | None = None
    volume: float | None = None
    poids_net: float | None = None


class SupplierOfferCreateV2(BaseModel):
    company_id: str | None = None
    user_id: int | None = None
    catalog: CatalogCreateV2 | None = None
    catalog_ref: int | None = None
    product: ProductCreateV2


class ProductUpdateV2(BaseModel):
    catalog_ref: int | None = None
    client_sku: str | None = None
    product_type: str | None = None
    price: float | None = Field(None, ge=0)
    currency: str | None = None
    quantity: int | None = Field(None, ge=0)
    is_active: bool | None = None
    teinte: str | None = None
    type_de_produit: str | None = None
    gamme: str | None = None
    duree_garantie: str | None = None
    conditions_garantie: str | None = None
    piece_ouvrage_destination: str | None = None
    traitement_bois_classification: str | None = None
    produit_nuance: str | None = None
    description_profil: str | None = None
    couleur_traitement_autoclave: str | None = None
    code_douane_sh8: str | None = None
    type_bois: str | None = None
    essence_bois: str | None = None
    longueur: float | None = None
    largeur: float | None = None
    hauteur: float | None = None
    volume: float | None = None
    poids_net: float | None = None


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
