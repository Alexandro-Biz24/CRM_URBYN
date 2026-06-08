from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import User
from app.repositories import auth_repo, onboarding_company_repo
from app.schemas.onboarding_company import (
    OnboardingCompanyRequest,
    OnboardingCompanyResponse,
)
from app.services.auth import ROLE_BY_ACCOUNT_TYPE
from app.schemas.auth import AccountType


class OnboardingCompanyError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def list_company_options(db: Session) -> list[dict]:
    rows = onboarding_company_repo.list_companies_for_dropdown(db)
    return [
        {"tva_intra_com": tva, "company_name": name}
        for tva, name in rows
    ]


def complete_supplier_company(
    db: Session,
    payload: OnboardingCompanyRequest,
) -> OnboardingCompanyResponse:
    has_existing = payload.existing_company is not None
    has_new = payload.new_company is not None

    if has_existing == has_new:
        raise OnboardingCompanyError(
            "company_path",
            "Indiquez soit une société existante, soit une nouvelle société.",
        )

    user = db.scalar(
        select(User)
        .options(joinedload(User.role))
        .where(User.id == payload.user_id)
    )
    if user is None:
        raise OnboardingCompanyError("user_not_found", "Utilisateur introuvable.")

    if auth_repo.normalize_email(user.email) != auth_repo.normalize_email(str(payload.email)):
        raise OnboardingCompanyError("session_mismatch", "Session invalide.")

    if not user.email_verified:
        raise OnboardingCompanyError("email_not_verified", "Email non confirmé.")

    role_name = user.role.role_name if user.role else None
    if role_name != ROLE_BY_ACCOUNT_TYPE[AccountType.partner]:
        raise OnboardingCompanyError(
            "role_mismatch",
            "Cette étape est réservée aux comptes partenaire (fournisseur).",
        )

    if has_existing:
        return _link_existing_company(db, user, payload)
    return _create_new_company(db, user, payload)


def _link_existing_company(
    db: Session,
    user: User,
    payload: OnboardingCompanyRequest,
) -> OnboardingCompanyResponse:
    assert payload.existing_company is not None
    selected = onboarding_company_repo.normalize_tva(payload.existing_company.company_id)
    verification = onboarding_company_repo.normalize_tva(
        payload.existing_company.tva_verification
    )

    if selected != verification:
        raise OnboardingCompanyError(
            "tva_mismatch",
            "Le numéro de TVA ne correspond pas à la société sélectionnée.",
        )

    company = onboarding_company_repo.get_company(db, selected)
    if company is None:
        raise OnboardingCompanyError(
            "company_not_found",
            "Société introuvable. Créez une nouvelle fiche ci-dessous.",
        )

    if not onboarding_company_repo.user_has_company_membership(db, user.id, company.tva_intra_com):
        onboarding_company_repo.create_company_membership(db, user.id, company.tva_intra_com)

    db.commit()

    return OnboardingCompanyResponse(
        user_id=user.id,
        company_id=company.tva_intra_com,
        company_name=company.company_name,
        company_created=False,
        message="Vous êtes rattaché à la société existante.",
    )


def _create_new_company(
    db: Session,
    user: User,
    payload: OnboardingCompanyRequest,
) -> OnboardingCompanyResponse:
    assert payload.new_company is not None
    new_co = payload.new_company
    tva = onboarding_company_repo.normalize_tva(new_co.tva_intra_com)

    existing = onboarding_company_repo.get_company(db, tva)
    if existing is not None:
        # Société orpheline (ex. dernier user supprimé en admin) : rattacher au lieu de bloquer
        if not onboarding_company_repo.user_has_company_membership(db, user.id, existing.tva_intra_com):
            onboarding_company_repo.create_company_membership(db, user.id, existing.tva_intra_com)
        db.commit()
        return OnboardingCompanyResponse(
            user_id=user.id,
            company_id=existing.tva_intra_com,
            company_name=existing.company_name,
            company_created=False,
            message="Vous êtes rattaché à la société existante.",
        )

    company = onboarding_company_repo.create_company_with_addresses(db, new_co)

    if not onboarding_company_repo.user_has_company_membership(db, user.id, company.tva_intra_com):
        onboarding_company_repo.create_company_membership(db, user.id, company.tva_intra_com)

    db.commit()

    return OnboardingCompanyResponse(
        user_id=user.id,
        company_id=company.tva_intra_com,
        company_name=company.company_name,
        company_created=True,
        message="Société créée et rattachée à votre compte.",
    )
