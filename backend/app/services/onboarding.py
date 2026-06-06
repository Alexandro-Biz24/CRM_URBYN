from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Language, User, UserProfile
from app.repositories import auth_repo
from app.schemas.auth import AccountType
from app.schemas.onboarding import OnboardingProfileUpdate
from app.services.auth import user_to_session

ROLE_TO_ACCOUNT: dict[str, AccountType] = {
    "Client": AccountType.buyer,
    "Fournisseur": AccountType.partner,
}


class OnboardingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _account_type_for_user(user: User) -> AccountType:
    role_name = user.role.role_name if user.role else None
    if role_name not in ROLE_TO_ACCOUNT:
        raise OnboardingError("role_missing", "Rôle utilisateur introuvable.")
    return ROLE_TO_ACCOUNT[role_name]


def complete_user_profile(db: Session, payload: OnboardingProfileUpdate):
    stmt = (
        select(User)
        .options(joinedload(User.role), joinedload(User.profile))
        .where(User.id == payload.user_id)
    )
    user = db.scalar(stmt)

    if user is None:
        raise OnboardingError("user_not_found", "Utilisateur introuvable.")

    if auth_repo.normalize_email(user.email) != auth_repo.normalize_email(str(payload.email)):
        raise OnboardingError(
            "session_mismatch",
            "L'email ne correspond pas à cet utilisateur.",
        )

    if not user.email_verified:
        raise OnboardingError(
            "email_not_verified",
            "Confirmez votre email avant de compléter le profil.",
        )

    lang_exists = db.scalar(
        select(Language.id).where(Language.id == payload.language_id)
    )
    if lang_exists is None:
        raise OnboardingError(
            "language_not_found",
            f"La langue {payload.language_id} est introuvable.",
        )

    mobile = payload.mobile_phone.strip() if payload.mobile_phone else None
    if mobile:
        user.mobile_phone = mobile
    user.updated_at = datetime.utcnow()

    title = payload.title.strip()
    first_name = payload.first_name.strip()
    last_name = payload.last_name.strip()

    if user.profile is None:
        profile = UserProfile(
            user_id=user.id,
            language_id=payload.language_id,
            title=title,
            first_name=first_name,
            last_name=last_name,
        )
        db.add(profile)
    else:
        user.profile.language_id = payload.language_id
        user.profile.title = title
        user.profile.first_name = first_name
        user.profile.last_name = last_name
        user.profile.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(user)

    account_type = _account_type_for_user(user)
    session = user_to_session(user, account_type)
    return session, True
