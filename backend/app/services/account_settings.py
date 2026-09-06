from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.security import verify_password
from app.models import Address, Company, CompanyUser, User, UserProfile
from app.repositories import auth_repo, supplier_portal_repo as portal_repo
from app.schemas.client_orders import (
    AccountAddressUpdate,
    AccountAddressWrite,
    AccountEmailChangeConfirm,
    AccountEmailChangeStart,
    AccountPasswordChange,
    AccountProfileOut,
    AccountProfileUpdate,
    MessageOut,
)
from app.schemas.supplier_portal import PortalSession
from app.services.signup import SignupError, _dispatch_verification_email, _generate_code, _hash_code

PURPOSE_EMAIL_CHANGE = "email_change"


class AccountSettingsError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _require_user(db: Session, session: PortalSession) -> User:
    user = portal_repo.get_user(db, session.user_id, str(session.email))
    if user is None:
        raise AccountSettingsError("session_mismatch", "Session invalide.")
    return user


def _company_for_user(db: Session, user_id: int) -> tuple[str, str] | None:
    return portal_repo.get_company_for_user(db, user_id)


def get_account_profile(db: Session, session: PortalSession) -> AccountProfileOut:
    user = _require_user(db, session)
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    company_row = _company_for_user(db, user.id)
    addresses: list[dict] = []
    company_name = None
    company_tva = None
    if company_row:
        company_tva, company_name = company_row
        rows = db.scalars(
            select(Address)
            .where(Address.company_tva_intra_com == company_tva)
            .order_by(Address.is_primary.desc(), Address.id)
        ).all()
        addresses = [
            {
                "id": a.id,
                "type": a.type,
                "street": a.street,
                "city": a.city,
                "zip_code": a.zip_code,
                "state": a.state,
                "country_code": a.country_code,
                "is_primary": a.is_primary,
            }
            for a in rows
        ]

    role_name = user.role.role_name if user.role else ""
    account_type = "partner" if role_name == "Fournisseur" else "buyer"
    return AccountProfileOut(
        user_id=user.id,
        email=user.email,
        account_type=account_type,
        title=profile.title if profile else None,
        first_name=profile.first_name if profile else None,
        last_name=profile.last_name if profile else None,
        mobile_phone=user.mobile_phone,
        fixe_phone=user.fixe_phone,
        company_name=company_name,
        company_tva=company_tva,
        addresses=addresses,
    )


def update_account_profile(
    db: Session, payload: AccountProfileUpdate
) -> AccountProfileOut:
    user = _require_user(db, payload.session)
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    if profile is None:
        profile = UserProfile(user_id=user.id, language_id=1)
        db.add(profile)
        db.flush()

    if payload.title is not None:
        profile.title = payload.title.strip() or None
    if payload.first_name is not None:
        profile.first_name = payload.first_name.strip() or None
    if payload.last_name is not None:
        profile.last_name = payload.last_name.strip() or None
    if payload.mobile_phone is not None:
        user.mobile_phone = payload.mobile_phone.strip() or None
    if payload.fixe_phone is not None:
        user.fixe_phone = payload.fixe_phone.strip() or None
    profile.updated_at = datetime.utcnow()
    user.updated_at = datetime.utcnow()
    db.commit()
    return get_account_profile(db, payload.session)


def change_password(db: Session, payload: AccountPasswordChange) -> MessageOut:
    user = _require_user(db, payload.session)
    if payload.new_password != payload.confirm_password:
        raise AccountSettingsError(
            "password_mismatch", "Les nouveaux mots de passe ne correspondent pas."
        )
    if len(payload.new_password) < 8:
        raise AccountSettingsError(
            "weak_password", "Le mot de passe doit contenir au moins 8 caractères."
        )
    if not verify_password(payload.current_password, user.password_hash):
        raise AccountSettingsError(
            "invalid_password", "Mot de passe actuel incorrect."
        )
    auth_repo.update_user_password(db, user.id, payload.new_password)
    db.commit()
    return MessageOut(message="Mot de passe mis à jour.")


def start_email_change(db: Session, payload: AccountEmailChangeStart) -> MessageOut:
    user = _require_user(db, payload.session)
    new_email = auth_repo.normalize_email(str(payload.new_email))
    if new_email == auth_repo.normalize_email(user.email):
        raise AccountSettingsError("same_email", "Cet email est déjà le vôtre.")
    if auth_repo.email_exists_for_role(db, new_email, user.role_id):
        raise AccountSettingsError(
            "email_taken", "Un compte avec cet email existe déjà pour ce rôle."
        )

    code = _generate_code()
    ttl = settings.VERIFICATION_CODE_TTL_SECONDS
    expires_at = datetime.utcnow() + timedelta(seconds=ttl)
    auth_repo.invalidate_pending_codes(db, user.id, purpose=PURPOSE_EMAIL_CHANGE)
    auth_repo.create_verification_code(
        db,
        user_id=user.id,
        code_hash=_hash_code(code),
        expires_at=expires_at,
        purpose=PURPOSE_EMAIL_CHANGE,
        payload=new_email,
    )
    db.commit()
    _dispatch_verification_email(
        to_email=new_email,
        code=code,
        ttl_minutes=max(1, ttl // 60),
    )
    return MessageOut(
        message="Un code de confirmation a été envoyé à la nouvelle adresse email.",
        expires_in_seconds=ttl,
    )


def confirm_email_change(
    db: Session, payload: AccountEmailChangeConfirm
) -> AccountProfileOut:
    user = _require_user(db, payload.session)
    record = auth_repo.get_latest_valid_code(
        db, user.id, purpose=PURPOSE_EMAIL_CHANGE
    )
    if record is None:
        raise AccountSettingsError(
            "code_expired", "Code expiré ou introuvable. Demandez un nouveau code."
        )
    from app.core.security import verify_password as _vp

    if not _vp(payload.code, record.code_hash):
        # codes are hashed with hash_password — verify_password works
        raise AccountSettingsError("invalid_code", "Code incorrect.")

    new_email = (record.payload or "").strip().lower()
    if not new_email:
        raise AccountSettingsError("invalid_payload", "Email cible manquant.")
    if auth_repo.email_exists_for_role(db, new_email, user.role_id):
        raise AccountSettingsError(
            "email_taken", "Un compte avec cet email existe déjà pour ce rôle."
        )

    db.execute(
        update(User)
        .where(User.id == user.id)
        .values(email=new_email, updated_at=datetime.utcnow())
    )
    auth_repo.mark_code_used(db, record.id)
    db.commit()
    # session email must be updated by caller
    new_session = PortalSession(user_id=user.id, email=new_email)
    return get_account_profile(db, new_session)


def add_address(db: Session, payload: AccountAddressWrite) -> AccountProfileOut:
    user = _require_user(db, payload.session)
    company = _company_for_user(db, user.id)
    if company is None:
        raise AccountSettingsError(
            "no_company", "Aucune société rattachée : impossible d'ajouter une adresse."
        )
    company_tva, _ = company
    if payload.is_primary:
        db.execute(
            update(Address)
            .where(Address.company_tva_intra_com == company_tva)
            .values(is_primary=False)
        )
    addr = Address(
        company_tva_intra_com=company_tva,
        type=(payload.type or "delivery").strip()[:32],
        street=payload.street,
        city=payload.city,
        zip_code=payload.zip_code,
        state=payload.state,
        country_code=(payload.country_code or "FR")[:2],
        is_primary=payload.is_primary,
    )
    db.add(addr)
    db.commit()
    return get_account_profile(db, payload.session)


def update_address(db: Session, payload: AccountAddressUpdate) -> AccountProfileOut:
    user = _require_user(db, payload.session)
    company = _company_for_user(db, user.id)
    if company is None:
        raise AccountSettingsError("no_company", "Aucune société rattachée.")
    company_tva, _ = company
    addr = db.scalar(
        select(Address).where(
            Address.id == payload.address_id,
            Address.company_tva_intra_com == company_tva,
        )
    )
    if addr is None:
        raise AccountSettingsError("not_found", "Adresse introuvable.")
    if payload.is_primary:
        db.execute(
            update(Address)
            .where(Address.company_tva_intra_com == company_tva)
            .values(is_primary=False)
        )
    addr.type = (payload.type or addr.type).strip()[:32]
    addr.street = payload.street
    addr.city = payload.city
    addr.zip_code = payload.zip_code
    addr.state = payload.state
    addr.country_code = (payload.country_code or addr.country_code or "FR")[:2]
    addr.is_primary = payload.is_primary
    addr.updated_at = datetime.utcnow()
    db.commit()
    return get_account_profile(db, payload.session)


def delete_address(
    db: Session, session: PortalSession, address_id: int
) -> AccountProfileOut:
    user = _require_user(db, session)
    company = _company_for_user(db, user.id)
    if company is None:
        raise AccountSettingsError("no_company", "Aucune société rattachée.")
    company_tva, _ = company
    addr = db.scalar(
        select(Address).where(
            Address.id == address_id,
            Address.company_tva_intra_com == company_tva,
        )
    )
    if addr is None:
        raise AccountSettingsError("not_found", "Adresse introuvable.")
    db.delete(addr)
    db.commit()
    return get_account_profile(db, session)
