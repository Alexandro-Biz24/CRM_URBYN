from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.repositories import auth_repo
from app.schemas.auth import AccountType, SessionUser
from app.services.auth import ROLE_BY_ACCOUNT_TYPE, user_to_session
from app.services.email_sender import EmailDeliveryError, send_verification_email

CODE_LENGTH = 6
logger = logging.getLogger(__name__)


def _generate_code() -> str:
    return f"{secrets.randbelow(10**CODE_LENGTH):06d}"


def _hash_code(code: str) -> str:
    return hash_password(code)


class SignupError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _role_id_for_account_type(db: Session, account_type: AccountType) -> int:
    role_name = ROLE_BY_ACCOUNT_TYPE[account_type]
    role_id = auth_repo.get_role_id_by_name(db, role_name)
    if role_id is None:
        raise SignupError(
            "role_missing",
            f"Le rôle « {role_name} » est introuvable en base.",
        )
    return role_id


def check_email_availability(db: Session, email: str, account_type: AccountType) -> dict:
    role_id = _role_id_for_account_type(db, account_type)
    user = auth_repo.get_user_by_email_and_role_id(db, email, role_id)
    if user is None:
        return {"exists": False, "available": True, "email_verified": None}
    return {
        "exists": True,
        "available": False,
        "email_verified": user.email_verified,
    }


def _dispatch_verification_email(
    *,
    to_email: str,
    code: str,
    ttl_minutes: int,
    account_type: AccountType | None = None,
) -> None:
    if settings.APP_ENV == "development":
        role_label = account_type.value if account_type else "?"
        logger.warning(
            "DEV — code OTP pour %s (%s) : %s (valable %s min)",
            to_email,
            role_label,
            code,
            ttl_minutes,
        )
    try:
        send_verification_email(to_email=to_email, code=code, ttl_minutes=ttl_minutes)
    except EmailDeliveryError as exc:
        raise SignupError("email_delivery_failed", str(exc)) from exc


def start_signup(db: Session, *, email: str, password: str, account_type: AccountType) -> dict:
    if len(password) < 8:
        raise SignupError("weak_password", "Le mot de passe doit contenir au moins 8 caractères.")

    role_id = _role_id_for_account_type(db, account_type)
    if auth_repo.email_exists_for_role(db, email, role_id):
        label = "client" if account_type == AccountType.buyer else "partenaire"
        raise SignupError(
            "email_taken",
            f"Un compte {label} existe déjà avec cet email.",
        )

    user = auth_repo.create_pending_user(
        db,
        email=email,
        raw_password=password,
        role_id=role_id,
    )

    code = _generate_code()
    ttl = settings.VERIFICATION_CODE_TTL_SECONDS
    expires_at = datetime.utcnow() + timedelta(seconds=ttl)
    ttl_minutes = max(1, ttl // 60)

    auth_repo.invalidate_pending_codes(db, user.id)
    auth_repo.create_verification_code(
        db,
        user_id=user.id,
        code_hash=_hash_code(code),
        expires_at=expires_at,
    )

    try:
        _dispatch_verification_email(
            to_email=user.email,
            code=code,
            ttl_minutes=ttl_minutes,
            account_type=account_type,
        )
    except SignupError:
        db.rollback()
        raise

    db.commit()

    return {
        "user_id": user.id,
        "email": user.email,
        "expires_in_seconds": ttl,
        "message": "Un code à 6 chiffres a été envoyé à votre adresse email.",
    }


def verify_signup_code(
    db: Session,
    *,
    email: str,
    code: str,
    account_type: AccountType,
) -> SessionUser:
    normalized_code = code.strip()
    if len(normalized_code) != CODE_LENGTH or not normalized_code.isdigit():
        raise SignupError("invalid_code_format", "Le code doit contenir exactement 6 chiffres.")

    role_id = _role_id_for_account_type(db, account_type)
    user = auth_repo.get_user_with_role_profile_by_role_id(db, email, role_id)
    if user is None:
        raise SignupError("user_not_found", "Compte introuvable.")

    if user.email_verified:
        return user_to_session(user, account_type)

    record = auth_repo.get_latest_valid_code(db, user.id)
    if record is None:
        raise SignupError(
            "code_expired",
            "Code expiré ou invalide. Demandez un nouveau code.",
        )

    if record.code_hash != _hash_code(normalized_code):
        raise SignupError("invalid_code", "Code incorrect.")

    auth_repo.mark_code_used(db, record.id)
    auth_repo.mark_email_verified(db, user.id)
    db.commit()

    db.refresh(user)
    return user_to_session(user, account_type)


def resend_verification_code(
    db: Session,
    *,
    email: str,
    password: str,
    account_type: AccountType,
) -> dict:
    role_id = _role_id_for_account_type(db, account_type)
    user = auth_repo.get_user_by_email_and_role_id(db, email, role_id)
    if user is None:
        raise SignupError("user_not_found", "Compte introuvable.")

    if not verify_password(password, user.password_hash):
        raise SignupError("invalid_credentials", "Mot de passe incorrect.")

    if user.email_verified:
        raise SignupError("already_verified", "Cet email est déjà vérifié.")

    code = _generate_code()
    ttl = settings.VERIFICATION_CODE_TTL_SECONDS
    expires_at = datetime.utcnow() + timedelta(seconds=ttl)
    ttl_minutes = max(1, ttl // 60)

    auth_repo.invalidate_pending_codes(db, user.id)
    auth_repo.create_verification_code(
        db,
        user_id=user.id,
        code_hash=_hash_code(code),
        expires_at=expires_at,
    )

    try:
        _dispatch_verification_email(
            to_email=user.email,
            code=code,
            ttl_minutes=ttl_minutes,
            account_type=account_type,
        )
    except SignupError:
        db.rollback()
        raise

    db.commit()

    return {
        "expires_in_seconds": ttl,
        "message": "Un nouveau code a été envoyé à votre adresse email.",
    }
