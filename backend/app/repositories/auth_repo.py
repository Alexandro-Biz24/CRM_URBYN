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


def get_user_by_email_and_role_id(db: Session, email: str, role_id: int) -> User | None:
    normalized = normalize_email(email)
    stmt = select(User).where(
        func.lower(User.email) == normalized,
        User.role_id == role_id,
    )
    return db.scalar(stmt)


def get_user_with_role_profile(db: Session, email: str) -> User | None:
    normalized = normalize_email(email)
    stmt = (
        select(User)
        .options(joinedload(User.role), joinedload(User.profile))
        .where(func.lower(User.email) == normalized)
    )
    return db.scalar(stmt)


def get_user_with_role_profile_by_role_id(
    db: Session,
    email: str,
    role_id: int,
) -> User | None:
    normalized = normalize_email(email)
    stmt = (
        select(User)
        .options(joinedload(User.role), joinedload(User.profile))
        .where(func.lower(User.email) == normalized, User.role_id == role_id)
    )
    return db.scalar(stmt)


def email_exists(db: Session, email: str) -> bool:
    return get_user_by_email(db, email) is not None


def email_exists_for_role(db: Session, email: str, role_id: int) -> bool:
    return get_user_by_email_and_role_id(db, email, role_id) is not None


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


def invalidate_pending_codes(
    db: Session,
    user_id: int,
    *,
    purpose: str | None = None,
) -> None:
    now = datetime.utcnow()
    cond = [
        EmailVerificationCode.user_id == user_id,
        EmailVerificationCode.used_at.is_(None),
    ]
    if purpose is not None:
        cond.append(EmailVerificationCode.purpose == purpose)
    db.execute(update(EmailVerificationCode).where(*cond).values(used_at=now))


def create_verification_code(
    db: Session,
    *,
    user_id: int,
    code_hash: str,
    expires_at: datetime,
    purpose: str | None = None,
    payload: str | None = None,
) -> EmailVerificationCode:
    record = EmailVerificationCode(
        user_id=user_id,
        code_hash=code_hash,
        expires_at=expires_at,
        purpose=purpose,
        payload=payload,
    )
    db.add(record)
    db.flush()
    return record


def get_latest_valid_code(
    db: Session,
    user_id: int,
    *,
    purpose: str | None = None,
) -> EmailVerificationCode | None:
    now = datetime.utcnow()
    cond = [
        EmailVerificationCode.user_id == user_id,
        EmailVerificationCode.used_at.is_(None),
        EmailVerificationCode.expires_at > now,
    ]
    if purpose is not None:
        cond.append(EmailVerificationCode.purpose == purpose)
    else:
        # Compat anciens flux signup/reset (purpose NULL)
        cond.append(EmailVerificationCode.purpose.is_(None))
    stmt = (
        select(EmailVerificationCode)
        .where(*cond)
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


def update_user_password(db: Session, user_id: int, raw_password: str) -> None:
    db.execute(
        update(User)
        .where(User.id == user_id)
        .values(password_hash=hash_password(raw_password), updated_at=datetime.utcnow())
    )
