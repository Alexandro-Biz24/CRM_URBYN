from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Address, Company, CompanyUser
from app.schemas.onboarding_company import OnboardingAddressInput, OnboardingNewCompanyInput


def normalize_tva(tva: str) -> str:
    return tva.strip().upper().replace(" ", "")


def list_companies_for_dropdown(db: Session, *, limit: int = 200) -> list[tuple[str, str]]:
    """Toutes les sociétés en base (y compris sans utilisateur lié après suppression admin)."""
    stmt = (
        select(Company.tva_intra_com, Company.company_name)
        .order_by(Company.company_name)
        .limit(limit)
    )
    return [(r[0], r[1]) for r in db.execute(stmt).all()]


def get_company(db: Session, tva: str) -> Company | None:
    normalized = normalize_tva(tva)
    company = db.get(Company, normalized)
    if company is not None:
        return company
    stmt = select(Company).where(func.upper(Company.tva_intra_com) == normalized)
    return db.scalar(stmt)


def user_has_company_membership(db: Session, user_id: int, tva: str) -> bool:
    company = get_company(db, tva)
    if company is None:
        return False
    stmt = select(CompanyUser.id).where(
        CompanyUser.user_id == user_id,
        CompanyUser.company_tva_intra_com == company.tva_intra_com,
    )
    return db.scalar(stmt) is not None


def create_company_membership(db: Session, user_id: int, tva: str) -> None:
    link = CompanyUser(user_id=user_id, company_tva_intra_com=tva.strip())
    db.add(link)
    db.flush()


def create_company_with_addresses(
    db: Session,
    payload: OnboardingNewCompanyInput,
) -> Company:
    company = Company(
        tva_intra_com=normalize_tva(payload.tva_intra_com),
        company_name=payload.company_name.strip(),
        phone_number=payload.phone_number,
        code_naf=payload.code_naf.strip(),
        email=payload.email,
        website=payload.website,
        cgv_accepted=payload.cgv_accepted,
        is_verified=False,
    )
    db.add(company)
    db.flush()

    for idx, addr in enumerate(payload.addresses):
        _create_address(db, company.tva_intra_com, addr, is_primary=(idx == 0))

    return company


def _create_address(
    db: Session,
    company_tva: str,
    addr: OnboardingAddressInput,
    *,
    is_primary: bool,
) -> None:
    db.add(
        Address(
            company_tva_intra_com=company_tva,
            type=addr.type.strip(),
            street=addr.street.strip(),
            city=addr.city.strip(),
            zip_code=addr.zip_code.strip(),
            state=addr.state.strip() if addr.state else None,
            country_code=(addr.country_code or "FR").upper()[:2],
            siret=addr.siret,
            is_primary=is_primary or addr.is_primary,
        )
    )
    db.flush()
