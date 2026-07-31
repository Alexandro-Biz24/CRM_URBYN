from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories import admin_accounts_repo as repo
from app.schemas.admin_accounts import (
    AdminAddressOut,
    AdminCompaniesListResponse,
    AdminCompanyDetail,
    AdminCompanyListItem,
    AdminCompanyUserOut,
    AdminUserCompanyLink,
    AdminUserDetail,
    AdminUserListItem,
    AdminUsersListResponse,
)


class AdminAccountsError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def list_users(db: Session) -> AdminUsersListResponse:
    suppliers, clients = repo.list_users_by_role(db)
    return AdminUsersListResponse(
        suppliers=[AdminUserListItem(**u) for u in suppliers],
        clients=[AdminUserListItem(**u) for u in clients],
    )


def get_user(db: Session, user_id: int) -> AdminUserDetail:
    user = repo.get_user_detail(db, user_id)
    if user is None:
        raise AdminAccountsError("not_found", "Utilisateur introuvable.")
    profile = user.profile
    companies = [
        AdminUserCompanyLink(
            tva_intra_com=cu.company.tva_intra_com,
            company_name=cu.company.company_name,
        )
        for cu in user.company_memberships
        if cu.company is not None
    ]
    return AdminUserDetail(
        id=user.id,
        email=user.email,
        role=user.role.role_name if user.role else None,
        first_name=profile.first_name if profile else None,
        last_name=profile.last_name if profile else None,
        title=profile.title if profile else None,
        mobile_phone=user.mobile_phone,
        fixe_phone=user.fixe_phone,
        is_active=user.is_active,
        email_verified=user.email_verified,
        created_at=user.created_at.isoformat(),
        updated_at=user.updated_at.isoformat(),
        companies=companies,
    )


def delete_user(db: Session, user_id: int) -> None:
    if repo.get_user_detail(db, user_id) is None:
        raise AdminAccountsError("not_found", "Utilisateur introuvable.")
    try:
        repo.delete_user(db, user_id)
        db.commit()
    except Exception:
        db.rollback()
        raise


def list_companies(db: Session) -> AdminCompaniesListResponse:
    suppliers, clients = repo.list_companies_by_side(db)
    return AdminCompaniesListResponse(
        suppliers=[AdminCompanyListItem(**c) for c in suppliers],
        clients=[AdminCompanyListItem(**c) for c in clients],
    )


def get_company(db: Session, tva: str) -> AdminCompanyDetail:
    company = repo.get_company_detail(db, tva.strip())
    if company is None:
        raise AdminAccountsError("not_found", "Société introuvable.")
    users = []
    for cu in company.company_users:
        u = cu.user
        if u is None:
            continue
        prof = u.profile
        users.append(
            AdminCompanyUserOut(
                id=u.id,
                email=u.email,
                first_name=prof.first_name if prof else None,
                last_name=prof.last_name if prof else None,
                role=u.role.role_name if u.role else None,
            )
        )
    return AdminCompanyDetail(
        tva_intra_com=company.tva_intra_com,
        company_name=company.company_name,
        email=company.email,
        phone_number=company.phone_number,
        code_naf=company.code_naf,
        branche=company.branche,
        website=company.website,
        description=company.description,
        condition_reglement=company.condition_reglement,
        vat_rate=float(company.vat_rate) if company.vat_rate is not None else None,
        is_verified=company.is_verified,
        cgv_accepted=company.cgv_accepted,
        created_at=company.created_at.isoformat(),
        updated_at=company.updated_at.isoformat(),
        addresses=[
            AdminAddressOut(
                id=a.id,
                type=a.type,
                street=a.street,
                city=a.city,
                zip_code=a.zip_code,
                country_code=a.country_code,
                is_primary=a.is_primary,
            )
            for a in company.addresses
        ],
        users=users,
        product_count=repo.count_company_products(db, company.tva_intra_com),
        shipping_rate_count=repo.count_company_shipping(db, company.tva_intra_com),
        payment_method_count=repo.count_company_payments(db, company.tva_intra_com),
    )


def delete_company(db: Session, tva: str) -> None:
    try:
        repo.delete_company(db, tva.strip())
        db.commit()
    except ValueError as exc:
        db.rollback()
        if str(exc) == "not_found":
            raise AdminAccountsError("not_found", "Société introuvable.") from exc
        raise
