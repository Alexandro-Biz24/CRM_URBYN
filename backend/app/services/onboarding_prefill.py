from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import Address, Company, CompanyUser, User
from app.repositories import auth_repo
from app.schemas.onboarding_company import OnboardingAddressInput
from app.schemas.onboarding_prefill import (
    SiblingCompanyPrefill,
    SiblingOnboardingPrefillResponse,
    SiblingProfilePrefill,
)


def _address_to_input(addr: Address) -> OnboardingAddressInput:
    return OnboardingAddressInput(
        type=addr.type or "Siège social",
        street=addr.street or "",
        city=addr.city or "",
        zip_code=addr.zip_code or "",
        state=addr.state,
        country_code=addr.country_code or "FR",
        siret=addr.siret,
        is_primary=addr.is_primary,
    )


def get_sibling_onboarding_prefill(
    db: Session,
    *,
    user_id: int,
    email: str,
) -> SiblingOnboardingPrefillResponse:
    user = db.scalar(
        select(User)
        .options(joinedload(User.role), joinedload(User.profile))
        .where(User.id == user_id)
    )
    if user is None:
        return SiblingOnboardingPrefillResponse(has_sibling=False)

    if auth_repo.normalize_email(user.email) != auth_repo.normalize_email(email):
        return SiblingOnboardingPrefillResponse(has_sibling=False)

    stmt = (
        select(User)
        .options(
            joinedload(User.role),
            joinedload(User.profile),
            joinedload(User.company_memberships).joinedload(CompanyUser.company).joinedload(
                Company.addresses
            ),
        )
        .where(
            func.lower(User.email) == auth_repo.normalize_email(email),
            User.id != user_id,
        )
    )
    sibling = db.scalar(stmt)
    if sibling is None:
        return SiblingOnboardingPrefillResponse(has_sibling=False)

    profile_prefill: SiblingProfilePrefill | None = None
    if sibling.profile is not None:
        profile_prefill = SiblingProfilePrefill(
            title=sibling.profile.title,
            first_name=sibling.profile.first_name,
            last_name=sibling.profile.last_name,
            mobile_phone=sibling.mobile_phone,
            language_id=sibling.profile.language_id,
        )

    company_prefill: SiblingCompanyPrefill | None = None
    if sibling.company_memberships:
        membership = sibling.company_memberships[-1]
        company = membership.company
        if company is not None:
            addresses = [_address_to_input(a) for a in company.addresses]
            company_prefill = SiblingCompanyPrefill(
                affiliation_mode="existing",
                tva_intra_com=company.tva_intra_com,
                company_name=company.company_name,
                code_naf=company.code_naf,
                email=company.email,
                phone_number=company.phone_number,
                website=company.website,
                addresses=addresses,
            )

    return SiblingOnboardingPrefillResponse(
        has_sibling=True,
        profile=profile_prefill,
        company=company_prefill,
    )
