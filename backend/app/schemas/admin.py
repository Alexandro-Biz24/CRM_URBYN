from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    login: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class AdminLoginResponse(BaseModel):
    token: str
    expires_at: int


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


class AdminCatalogUpdate(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    is_active: bool = True
