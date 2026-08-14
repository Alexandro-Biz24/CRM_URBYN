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
    breadcrumb: list[str] = Field(default_factory=list)


class CatalogAttributeDefinitionOut(BaseModel):
    id: int
    catalog_id: int
    attribute_name: str
    default_value: str = ""


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


class MandatoryAttributeValueOut(BaseModel):
    definition_id: int
    catalog_id: int
    attribute_name: str
    value: str | None


class MandatoryAttributeValueWrite(BaseModel):
    definition_id: int
    value: str = Field(..., min_length=1)


class ProductOut(BaseModel):
    id: int
    admin_sku: str
    primary_catalog_id: int
    catalog_ids: list[int]
    linked_catalogs: list[CatalogOut] = Field(default_factory=list)
    client_sku: str
    product_name: str
    price: float
    currency: str
    is_active: bool
    mandatory_attributes: list[MandatoryAttributeValueOut] = []


class ProductWrite(BaseModel):
    session: PortalSession
    primary_catalog_id: int
    additional_catalog_ids: list[int] = Field(default_factory=list)
    client_sku: str = Field(..., min_length=1)
    product_name: str = Field(..., min_length=1)
    price: float = Field(..., ge=0)
    currency: str = Field(..., min_length=3, max_length=3)
    is_active: bool = True
    mandatory_attributes: list[MandatoryAttributeValueWrite] = Field(default_factory=list)


class ProductListEntry(BaseModel):
    product_id: int
    admin_sku: str
    client_sku: str
    product_name: str
    primary_catalog_id: int
    catalog_name: str | None
    price: float
    currency: str
    is_active: bool


class ProductCatalogGroup(BaseModel):
    catalog_id: int
    catalog_name: str | None
    products: list[ProductListEntry] = Field(default_factory=list)


class ProductCatalogGroupsResponse(BaseModel):
    groups: list[ProductCatalogGroup] = Field(default_factory=list)


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
