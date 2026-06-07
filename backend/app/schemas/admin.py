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
