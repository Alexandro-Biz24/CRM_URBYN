from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, joinedload

from app.core.security import hash_password
from app.models import EmailVerificationCode, Role, User


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_user_by_email(db: Session, email: str) -> User | None:
    normalized = normalize_email(email)
    stmt = select(User).where(func.lower(User.email) == normalized)
    return db.scalar(stmt)


def get_user_with_role_profile(db: Session, email: str) -> User | None:
    normalized = normalize_email(email)
    stmt = (
        select(User)
        .options(joinedload(User.role), joinedload(User.profile))
        .where(func.lower(User.email) == normalized)
    )
    return db.scalar(stmt)


def email_exists(db: Session, email: str) -> bool:
    return get_user_by_email(db, email) is not None


def get_role_id_by_name(db: Session, role_name: str) -> int | None:
    role = db.scalar(select(Role).where(Role.role_name == role_name))
    return role.id if role else None


def create_pending_user(
    db: Session,
    *,
    email: str,
    raw_password: str,
    role_id: int,
) -> User:
    user = User(
        email=normalize_email(email),
        password_hash=hash_password(raw_password),
        role_id=role_id,
        is_active=True,
        email_verified=False,
    )
    db.add(user)
    db.flush()
    return user


def mark_email_verified(db: Session, user_id: int) -> None:
    db.execute(
        update(User)
        .where(User.id == user_id)
        .values(email_verified=True, updated_at=datetime.utcnow())
    )


def invalidate_pending_codes(db: Session, user_id: int) -> None:
    now = datetime.utcnow()
    db.execute(
        update(EmailVerificationCode)
        .where(
            EmailVerificationCode.user_id == user_id,
            EmailVerificationCode.used_at.is_(None),
        )
        .values(used_at=now)
    )


def create_verification_code(
    db: Session,
    *,
    user_id: int,
    code_hash: str,
    expires_at: datetime,
) -> EmailVerificationCode:
    record = EmailVerificationCode(
        user_id=user_id,
        code_hash=code_hash,
        expires_at=expires_at,
    )
    db.add(record)
    db.flush()
    return record


def get_latest_valid_code(db: Session, user_id: int) -> EmailVerificationCode | None:
    now = datetime.utcnow()
    stmt = (
        select(EmailVerificationCode)
        .where(
            EmailVerificationCode.user_id == user_id,
            EmailVerificationCode.used_at.is_(None),
            EmailVerificationCode.expires_at > now,
        )
        .order_by(EmailVerificationCode.created_at.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def mark_code_used(db: Session, code_id: int) -> None:
    db.execute(
        update(EmailVerificationCode)
        .where(EmailVerificationCode.id == code_id)
        .values(used_at=datetime.utcnow())
    )
