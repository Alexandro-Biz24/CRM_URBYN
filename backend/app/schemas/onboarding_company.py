from pydantic import BaseModel, EmailStr, Field


class CompanyOption(BaseModel):
    tva_intra_com: str
    company_name: str


class OnboardingAddressInput(BaseModel):
    type: str = Field(..., min_length=1, description="siège social, entrepôt, local ou personnalisé")
    street: str = Field(..., min_length=1, description="Rue")
    city: str = Field(..., min_length=1, description="Ville")
    zip_code: str = Field(..., min_length=1, description="Code postal")
    state: str | None = Field(None, description="Département / région")
    country_code: str = Field("FR", min_length=2, max_length=2, description="Code pays ISO")
    siret: str | None = None
    is_primary: bool = False


class OnboardingExistingCompanyInput(BaseModel):
    company_id: str = Field(..., description="TVA intracom de la société sélectionnée")
    tva_verification: str = Field(
        ...,
        description="TVA saisie par l'utilisateur pour confirmer l'affiliation",
    )


class OnboardingNewCompanyInput(BaseModel):
    company_name: str = Field(..., min_length=1)
    tva_intra_com: str = Field(..., min_length=4)
    code_naf: str = Field(..., min_length=1)
    addresses: list[OnboardingAddressInput] = Field(
        ...,
        min_length=1,
        max_length=3,
    )
    email: str | None = None
    phone_number: str | None = None
    website: str | None = None
    cgv_accepted: bool = True


class OnboardingCompanyRequest(BaseModel):
    user_id: int
    email: EmailStr
    existing_company: OnboardingExistingCompanyInput | None = None
    new_company: OnboardingNewCompanyInput | None = None


class EntrepriseSearchResult(BaseModel):
    company_name: str
    siren: str
    siret: str | None = None
    tva_intra_com: str | None = None
    code_naf: str | None = None
    street: str | None = None
    zip_code: str | None = None
    city: str | None = None
    state: str | None = None
    country_code: str = "FR"


class OnboardingCompanyResponse(BaseModel):
    user_id: int
    company_id: str
    company_name: str
    company_created: bool
    message: str
