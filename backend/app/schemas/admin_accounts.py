from pydantic import BaseModel


class AdminUserListItem(BaseModel):
    id: int
    email: str
    first_name: str | None
    last_name: str | None
    company_name: str | None
    company_tva: str | None
    is_active: bool
    email_verified: bool
    created_at: str


class AdminUsersListResponse(BaseModel):
    suppliers: list[AdminUserListItem]
    clients: list[AdminUserListItem]


class AdminUserCompanyLink(BaseModel):
    tva_intra_com: str
    company_name: str


class AdminUserDetail(BaseModel):
    id: int
    email: str
    role: str | None
    first_name: str | None
    last_name: str | None
    title: str | None
    mobile_phone: str | None
    fixe_phone: str | None
    is_active: bool
    email_verified: bool
    created_at: str
    updated_at: str
    companies: list[AdminUserCompanyLink]


class AdminCompanyListItem(BaseModel):
    tva_intra_com: str
    company_name: str
    email: str | None
    phone_number: str | None
    city: str | None
    country_code: str | None
    user_count: int
    product_count: int
    is_verified: bool
    created_at: str


class AdminCompaniesListResponse(BaseModel):
    suppliers: list[AdminCompanyListItem]
    clients: list[AdminCompanyListItem]


class AdminAddressOut(BaseModel):
    id: int
    type: str
    street: str | None
    city: str | None
    zip_code: str | None
    country_code: str | None
    is_primary: bool


class AdminCompanyUserOut(BaseModel):
    id: int
    email: str
    first_name: str | None
    last_name: str | None
    role: str | None


class AdminCompanyDetail(BaseModel):
    tva_intra_com: str
    company_name: str
    email: str | None
    phone_number: str | None
    code_naf: str | None
    branche: str | None
    website: str | None
    description: str | None
    condition_reglement: str | None
    vat_rate: float | None
    is_verified: bool
    cgv_accepted: bool
    created_at: str
    updated_at: str
    addresses: list[AdminAddressOut]
    users: list[AdminCompanyUserOut]
    product_count: int
    shipping_rate_count: int
    payment_method_count: int
