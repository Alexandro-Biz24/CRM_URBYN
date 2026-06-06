from pydantic import BaseModel, EmailStr, Field


class SupplierAddressCreateV2(BaseModel):
    type: str = Field(..., description="Type d'adresse (headquarter, delivery, etc.)")
    street: str | None = Field(None, description="Rue")
    city: str | None = Field(None, description="Ville")
    zip_code: str | None = Field(None, description="Code postal")
    state: str | None = Field(None, description="Région / État")
    country_code: str | None = Field(None, description="Code pays ISO 3166-1 alpha-2")
    siret: str | None = Field(None, description="SIRET")
    intra_com: str | None = Field(None, description="TVA intra au niveau adresse")
    lat: float | None = Field(None, description="Latitude")
    lng: float | None = Field(None, description="Longitude")
    is_primary: bool = Field(True, description="Adresse principale")


class SupplierExistingCompanyLinkInputV2(BaseModel):
    company_id: str = Field(
        ...,
        description="Identifiant société existante (companies.tva_intra_com)",
    )


class SupplierNewCompanyInputV2(BaseModel):
    tva_intra_com: str = Field(..., description="TVA intracommunautaire (PK companies)")
    company_name: str = Field(..., description="Nom société")
    phone_number: str | None = Field(None, description="Téléphone société")
    code_naf: str | None = Field(None, description="Code NAF")
    email: str | None = Field(None, description="Email société")
    condition_reglement: str | None = Field(None, description="Condition de règlement")
    branche: str | None = Field(None, description="Branche")
    extrait_kbis: str | None = Field(None, description="URL/chemin extrait KBIS")
    cgv_accepted: bool = Field(False, description="CGV acceptées")
    website: str | None = Field(None, description="Website")
    description: str | None = Field(None, description="Description")
    logo: str | None = Field(None, description="Logo")
    vat_rate: float | None = Field(None, description="Taux de TVA")
    address: SupplierAddressCreateV2 | None = Field(
        None,
        description="Adresse à créer en même temps que la société",
    )


class SupplierAccountCreateV2(BaseModel):
    # User
    email: EmailStr = Field(..., description="Email utilisateur")
    password: str = Field(..., min_length=8, description="Mot de passe utilisateur")
    mobile_phone: str | None = Field(None, description="Téléphone mobile")
    fixe_phone: str | None = Field(None, description="Téléphone fixe")

    # UserProfile
    language_id: int = Field(..., description="ID langue")
    first_name: str | None = Field(None, description="Prénom")
    last_name: str | None = Field(None, description="Nom")
    title: str | None = Field(None, description="Civilité")

    # Split chemin 1 / chemin 2
    existing_company: SupplierExistingCompanyLinkInputV2 | None = Field(
        None,
        description="Chemin 1: rattachement à une company déjà existante",
    )
    new_company: SupplierNewCompanyInputV2 | None = Field(
        None,
        description="Chemin 2: création d'une nouvelle company",
    )


class SupplierAccountCreatedV2(BaseModel):
    user_id: int
    role_id: int | None
    company_id: str = Field(description="TVA intracom de la société liée")
    email: EmailStr
    is_active: bool
    company_created: bool = Field(
        description="True si company créée via le chemin 2, sinon False"
    )

