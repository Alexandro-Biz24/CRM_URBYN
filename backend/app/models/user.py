from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"))
    mobile_phone: Mapped[str | None] = mapped_column(String(40))
    fixe_phone: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    role: Mapped["Role | None"] = relationship("Role", back_populates="users")
    profile: Mapped["UserProfile | None"] = relationship(
        "UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    company_memberships: Mapped[list["CompanyUser"]] = relationship(
        "CompanyUser", back_populates="user", cascade="all, delete-orphan"
    )
    company_payment_methods: Mapped[list["CompanyPaymentMethod"]] = relationship(
        "CompanyPaymentMethod", back_populates="user", cascade="all, delete-orphan"
    )
    orders_as_seller: Mapped[list["Order"]] = relationship(
        "Order",
        foreign_keys="Order.seller_id",
        back_populates="seller_user",
        cascade="all, delete-orphan",
    )
    orders_as_buyer: Mapped[list["Order"]] = relationship(
        "Order",
        foreign_keys="Order.buyer_id",
        back_populates="buyer_user",
        cascade="all, delete-orphan",
    )
    reviews: Mapped[list["Review"]] = relationship(
        "Review", back_populates="user", cascade="all, delete-orphan"
    )
    verification_codes: Mapped[list["EmailVerificationCode"]] = relationship(
        "EmailVerificationCode", back_populates="user", cascade="all, delete-orphan"
    )
