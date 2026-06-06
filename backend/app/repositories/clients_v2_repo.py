from __future__ import annotations

import hashlib
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import Address, Company, CompanyUser, Language, Role, User, UserProfile
from app.schemas.clients_v2 import (
    ClientAccountCreateV2,
    ClientAddressCreateV2,
    ClientNewCompanyInputV2,
)

ROLE_NAME_CLIENT = "Client"


def hash_password(raw_password: str) -> str:
    return hashlib.sha256(raw_password.encode("utf-8")).hexdigest()


def get_user_by_email(db: Session, email: str) -> User | None:
    stmt: Select[tuple[User]] = select(User).where(User.email == email)
    return db.scalar(stmt)


def get_company_by_tva(db: Session, company_tva_intra_com: str) -> Company | None:
    stmt: Select[tuple[Company]] = select(Company).where(
        Company.tva_intra_com == company_tva_intra_com.strip()
    )
    return db.scalar(stmt)


def get_role_id_by_name(db: Session, role_name: str) -> int | None:
    stmt: Select[tuple[Role]] = select(Role).where(Role.role_name == role_name)
    role = db.scalar(stmt)
    return role.id if role is not None else None


def get_client_role_id(db: Session) -> int | None:
    return get_role_id_by_name(db=db, role_name=ROLE_NAME_CLIENT)


def language_exists(db: Session, language_id: int) -> bool:
    stmt: Select[tuple[Language]] = select(Language).where(Language.id == language_id)
    return db.scalar(stmt) is not None


def create_user(db: Session, payload: ClientAccountCreateV2, role_id: int) -> User:
    user = User(
        email=str(payload.email),
        password_hash=hash_password(payload.password),
        role_id=role_id,
        mobile_phone=payload.mobile_phone,
        fixe_phone=payload.fixe_phone,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def create_user_profile(db: Session, user_id: int, payload: ClientAccountCreateV2) -> None:
    profile = UserProfile(
        user_id=user_id,
        language_id=payload.language_id,
        title=payload.title,
        first_name=payload.first_name,
        last_name=payload.last_name,
    )
    db.add(profile)
    db.flush()


def create_company(db: Session, payload: ClientNewCompanyInputV2) -> Company:
    company = Company(
        tva_intra_com=payload.tva_intra_com.strip(),
        company_name=payload.company_name,
        phone_number=payload.phone_number,
        code_naf=payload.code_naf,
        email=payload.email,
        condition_reglement=payload.condition_reglement,
        branche=payload.branche,
        extrait_kbis=payload.extrait_kbis,
        cgv_accepted=payload.cgv_accepted,
        website=payload.website,
        description=payload.description,
        logo=payload.logo,
        vat_rate=Decimal(str(payload.vat_rate)) if payload.vat_rate is not None else None,
        is_verified=False,
    )
    db.add(company)
    db.flush()
    return company


def create_company_address(
    db: Session,
    company_tva_intra_com: str,
    address: ClientAddressCreateV2,
) -> None:
    db_address = Address(
        company_tva_intra_com=company_tva_intra_com,
        type=address.type,
        street=address.street,
        city=address.city,
        zip_code=address.zip_code,
        state=address.state,
        country_code=address.country_code,
        siret=address.siret,
        intra_com=address.intra_com,
        lat=address.lat,
        lng=address.lng,
        is_primary=address.is_primary,
    )
    db.add(db_address)
    db.flush()


def create_company_membership(db: Session, user_id: int, company_tva_intra_com: str) -> None:
    link = CompanyUser(
        user_id=user_id,
        company_tva_intra_com=company_tva_intra_com,
    )
    db.add(link)
    db.flush()
