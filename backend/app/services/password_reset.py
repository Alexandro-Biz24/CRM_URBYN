from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import verify_password
from app.repositories import auth_repo
from app.schemas.auth import AccountType
from app.services.auth import ROLE_BY_ACCOUNT_TYPE
from app.services.signup import SignupError, _dispatch_verification_email, _generate_code, _hash_code

logger = logging.getLogger(__name__)


class PasswordResetError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _norm_name(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _role_id(db: Session, account_type: AccountType) -> int:
    role_name = ROLE_BY_ACCOUNT_TYPE[account_type]
    role_id = auth_repo.get_role_id_by_name(db, role_name)
    if role_id is None:
        raise PasswordResetError(
            "role_missing",
            f"Le rôle « {role_name} » est introuvable en base.",
        )
    return role_id


def start_password_reset(
    db: Session,
    *,
    email: str,
    first_name: str,
    last_name: str,
    account_type: AccountType,
) -> dict:
    if not first_name.strip() or not last_name.strip():
        raise PasswordResetError(
            "invalid_identity",
            "Prénom et nom sont requis pour réinitialiser le mot de passe.",
        )

    role_id = _role_id(db, account_type)
    user = auth_repo.get_user_with_role_profile_by_role_id(db, email, role_id)
    if user is None or not user.is_active:
        raise PasswordResetError(
            "identity_mismatch",
            "Aucune correspondance pour cet email / prénom / nom sur ce type de compte.",
        )

    profile = user.profile
    if profile is None:
        raise PasswordResetError(
            "identity_mismatch",
            "Profil incomplet : impossible de vérifier l'identité.",
        )

    if _norm_name(profile.first_name) != _norm_name(first_name) or _norm_name(
        profile.last_name
    ) != _norm_name(last_name):
        raise PasswordResetError(
            "identity_mismatch",
            "Aucune correspondance pour cet email / prénom / nom sur ce type de compte.",
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
    except SignupError as exc:
        db.rollback()
        raise PasswordResetError(exc.code, exc.message) from exc

    db.commit()
    return {
        "email": user.email,
        "expires_in_seconds": ttl,
        "message": "Un code de vérification a été envoyé par email.",
    }


def resend_password_reset_code(
    db: Session,
    *,
    email: str,
    first_name: str,
    last_name: str,
    account_type: AccountType,
) -> dict:
    return start_password_reset(
        db,
        email=email,
        first_name=first_name,
        last_name=last_name,
        account_type=account_type,
    )


def confirm_password_reset(
    db: Session,
    *,
    email: str,
    code: str,
    account_type: AccountType,
    new_password: str,
) -> dict:
    if len(new_password) < 8:
        raise PasswordResetError(
            "weak_password",
            "Le mot de passe doit contenir au moins 8 caractères.",
        )
    if not code.isdigit() or len(code) != 6:
        raise PasswordResetError("invalid_code", "Le code doit contenir 6 chiffres.")

    role_id = _role_id(db, account_type)
    user = auth_repo.get_user_with_role_profile_by_role_id(db, email, role_id)
    if user is None or not user.is_active:
        raise PasswordResetError("not_found", "Compte introuvable.")

    record = auth_repo.get_latest_valid_code(db, user.id)
    if record is None:
        raise PasswordResetError(
            "code_expired",
            "Code expiré ou inexistant. Demandez un nouveau code.",
        )
    if not verify_password(code, record.code_hash):
        raise PasswordResetError("invalid_code", "Code incorrect.")

    auth_repo.mark_code_used(db, record.id)
    auth_repo.update_user_password(db, user.id, new_password)
    if not user.email_verified:
        auth_repo.mark_email_verified(db, user.id)
    db.commit()

    return {"message": "Mot de passe mis à jour. Vous pouvez vous connecter."}
