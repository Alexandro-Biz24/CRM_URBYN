from pydantic import BaseModel, EmailStr

from app.schemas.onboarding_company import OnboardingAddressInput


class SiblingProfilePrefill(BaseModel):
    title: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    mobile_phone: str | None = None
    language_id: int | None = None


class SiblingCompanyPrefill(BaseModel):
    affiliation_mode: str | None = None
    tva_intra_com: str | None = None
    company_name: str | None = None
    code_naf: str | None = None
    email: str | None = None
    phone_number: str | None = None
    website: str | None = None
    addresses: list[OnboardingAddressInput] = []


class SiblingOnboardingPrefillResponse(BaseModel):
    has_sibling: bool
    profile: SiblingProfilePrefill | None = None
    company: SiblingCompanyPrefill | None = None
