from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    login: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class AdminLoginResponse(BaseModel):
    token: str
    expires_at: int


class AdminAttributeDefinitionOut(BaseModel):
    id: int
    attribute_name: str


class AdminCatalogNode(BaseModel):
    id: int
    name: str | None
    description: str | None
    is_active: bool
    parent_id: int | None
    child_count: int
    product_count: int
    children: list["AdminCatalogNode"] = []


class AdminCatalogDetail(BaseModel):
    id: int
    name: str | None
    description: str | None
    is_active: bool
    parent_id: int | None
    child_count: int
    product_count: int
    breadcrumb: list[str]
    attribute_definitions: list[AdminAttributeDefinitionOut] = []


class AdminCatalogTreeResponse(BaseModel):
    roots: list[AdminCatalogNode]
    total: int


class AdminCatalogWrite(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    is_active: bool = True
    parent_id: int | None = Field(
        None,
        description="Omettre ou null pour une racine ; sinon ID du parent.",
    )
    attribute_names: list[str] = Field(default_factory=list)


class AdminCatalogUpdate(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    is_active: bool = True
    attribute_names: list[str] = Field(default_factory=list)


class AdminCatalogProductEntry(BaseModel):
    product_id: int
    admin_sku: str
    product_name: str
    company_name: str
    price: float
    currency: str
    is_active: bool


class AdminProductAttributeOut(BaseModel):
    name: str
    value: str | None


class AdminProductDetail(BaseModel):
    id: int
    admin_sku: str
    client_sku: str
    product_name: str
    company_name: str
    company_tva: str
    price: float
    currency: str
    is_active: bool
    catalog_names: list[str] = []
    mandatory_attributes: list[AdminProductAttributeOut] = []
    free_attributes: list[AdminProductAttributeOut] = []
