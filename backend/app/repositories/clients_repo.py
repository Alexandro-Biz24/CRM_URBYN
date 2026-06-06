"""
Requêtes DB pour la création de comptes client (User + UserProfile + Company + companies_users).
"""
from __future__ import annotations

import hashlib

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import (
    Address,
    Company,
    CompanyUser,
    Role,
    User,
    UserProfile,
)
from app.schemas.clients import ClientAccountCreate, ClientAddressCreate

ROLE_CLIENT = "client"


def _hash_password(raw_password: str) -> str:
    """Hash du mot de passe (V1 : SHA-256). À remplacer par bcrypt/argon2 en prod."""
    return hashlib.sha256(raw_password.encode("utf-8")).hexdigest()


def get_user_by_email(db: Session, email: str) -> User | None:
    stmt: Select[tuple[User]] = select(User).where(User.email == email)
    return db.scalar(stmt)


def get_company_by_tva_intra_com(db: Session, tva: str) -> Company | None:
    stmt: Select[tuple[Company]] = select(Company).where(
        Company.tva_intra_com == tva.strip()
    )
    return db.scalar(stmt)


def get_role_id_by_name(db: Session, role_name: str) -> int | None:
    stmt: Select[tuple[Role]] = select(Role).where(Role.role_name == role_name)
    role = db.scalar(stmt)
    return role.id if role is not None else None


def _create_user(db: Session, data: ClientAccountCreate) -> User:
    mobile = data.mobile_phone or data.phone
    user = User(
        email=str(data.email),
        password_hash=_hash_password(data.password),
        role_id=get_role_id_by_name(db, ROLE_CLIENT),
        mobile_phone=mobile,
        fixe_phone=data.fixe_phone,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _create_user_profile(
    db: Session,
    user: User,
    data: ClientAccountCreate,
) -> UserProfile:
    profile = UserProfile(
        user_id=user.id,
        language_id=data.language_id,
        title=data.title,
        first_name=data.first_name,
        last_name=data.last_name,
    )
    db.add(profile)
    db.flush()
    return profile


def _create_company(db: Session, data: ClientAccountCreate) -> Company:
    company = Company(
        tva_intra_com=data.tva_intra_com.strip(),
        company_name=data.company_name,
        phone_number=data.mobile_phone or data.fixe_phone or data.phone,
        code_naf=data.code_naf,
        email=data.company_email,
        condition_reglement=data.condition_reglement,
        branche=data.branche,
        extrait_kbis=data.extrait_kbis,
        cgv_accepted=data.cgv_accepted,
        website=data.website,
        description=data.company_description,
        logo=data.logo,
        is_verified=False,
    )
    db.add(company)
    db.flush()
    return company


def _create_company_user(db: Session, user: User, company: Company) -> CompanyUser:
    link = CompanyUser(
        user_id=user.id,
        company_tva_intra_com=company.tva_intra_com,
    )
    db.add(link)
    db.flush()
    return link


def _create_address(
    db: Session,
    company: Company,
    address: ClientAddressCreate,
) -> Address:
    db_address = Address(
        company_tva_intra_com=company.tva_intra_com,
        type=address.type,
        street=address.street,
        city=address.city,
        zip_code=address.zip_code,
        state=address.state,
        country_code=address.country_code,
        siret=address.siret,
        intra_com=address.intra_communal,
        lat=None,
        lng=None,
        is_primary=address.is_primary,
    )
    db.add(db_address)
    db.flush()
    return db_address


def create_client_account(
    db: Session,
    data: ClientAccountCreate,
) -> tuple[User, Company]:
    """
    Crée : User, UserProfile, Company (PK tva_intra_com), CompanyUser,
    puis Address optionnelle.
    """
    user = _create_user(db=db, data=data)
    _create_user_profile(db=db, user=user, data=data)
    company = _create_company(db=db, data=data)
    _create_company_user(db=db, user=user, company=company)
    if data.address is not None:
        _create_address(db=db, company=company, address=data.address)
    return user, company
