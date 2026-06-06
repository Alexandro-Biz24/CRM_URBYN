from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.repositories import auth_repo
from app.schemas.auth import AccountType, LoginRequest, SessionUser

ROLE_BY_ACCOUNT_TYPE: dict[AccountType, str] = {
    AccountType.buyer: "Client",
    AccountType.partner: "Fournisseur",
}


class AuthError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def user_to_session(user, account_type: AccountType) -> SessionUser:
    profile = user.profile
    role_name = user.role.role_name if user.role is not None else None
    return SessionUser(
        user_id=user.id,
        email=user.email,
        role_id=user.role_id,
        role_name=role_name,
        account_type=account_type,
        first_name=profile.first_name if profile else None,
        last_name=profile.last_name if profile else None,
        mobile_phone=user.mobile_phone,
        fixe_phone=user.fixe_phone,
        is_active=user.is_active,
        email_verified=user.email_verified,
    )


def login(db: Session, payload: LoginRequest) -> SessionUser:
    user = auth_repo.get_user_with_role_profile(db, str(payload.email))

    if user is None:
        raise AuthError("invalid_credentials", "Email ou mot de passe incorrect.")

    if not user.is_active:
        raise AuthError("inactive_account", "Ce compte est désactivé.")

    if not verify_password(payload.password, user.password_hash):
        raise AuthError("invalid_credentials", "Email ou mot de passe incorrect.")

    if not user.email_verified:
        raise AuthError(
            "email_not_verified",
            "Votre email n'est pas encore confirmé. Vérifiez votre boîte mail ou renvoyez un code.",
        )

    expected_role = ROLE_BY_ACCOUNT_TYPE[payload.account_type]
    role_name = user.role.role_name if user.role is not None else None

    if role_name != expected_role:
        raise AuthError(
            "role_mismatch",
            f"Ce compte n'est pas enregistré en tant que {expected_role.lower()}.",
        )

    return user_to_session(user, payload.account_type)
