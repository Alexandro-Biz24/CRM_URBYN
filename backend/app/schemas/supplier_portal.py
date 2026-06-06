from pydantic import BaseModel, EmailStr, Field


class PortalSession(BaseModel):
    user_id: int
    email: EmailStr


class PortalContext(BaseModel):
    user_id: int
    company_id: str
    company_name: str


class CatalogOut(BaseModel):
    id: int
    name: str | None
    description: str | None
    is_active: bool
    parent_id: int | None


class CatalogWrite(BaseModel):
    session: PortalSession
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    is_active: bool = True
    parent_id: int | None = Field(
        None,
        description="ID parent ; null = racine (sera défini à id après création)",
    )


class CatalogUpdateBody(CatalogWrite):
    pass


class ProductOut(BaseModel):
    id: int
    admin_sku: str
    catalog_ref: int
    client_sku: str
    product_type: str
    price: float
    currency: str
    quantity: int
    is_active: bool
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
    hauteur: float | None = None
    largeur: float | None = None
    volume: float | None = None
    poids_net: float | None = None


class ProductWrite(BaseModel):
    session: PortalSession
    catalog_ref: int
    client_sku: str = Field(..., min_length=1)
    product_type: str = Field(..., min_length=1)
    price: float = Field(..., ge=0)
    currency: str = Field(..., min_length=3, max_length=3)
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
    hauteur: float | None = None
    largeur: float | None = None
    volume: float | None = None
    poids_net: float | None = None


class ProductListEntry(BaseModel):
    product_id: int
    admin_sku: str
    client_sku: str
    catalog_ref: int
    catalog_name: str | None
    price: float
    currency: str
    quantity: int
    is_active: bool


class ProductAttributOut(BaseModel):
    id: int
    name: str
    value: str | None


class ProductAttributWrite(BaseModel):
    session: PortalSession
    name: str = Field(..., min_length=1)
    value: str | None = None


class ProductAttributUpdateBody(ProductAttributWrite):
    pass
