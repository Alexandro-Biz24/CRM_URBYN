from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Company(Base):
    """
    Société identifiée par le numéro de TVA intracommunautaire (PK métier).
    """

    __tablename__ = "companies"

    tva_intra_com: Mapped[str] = mapped_column(String(32), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[str | None] = mapped_column(String(40))
    code_naf: Mapped[str | None] = mapped_column(String(10))
    email: Mapped[str | None] = mapped_column(String(320))
    condition_reglement: Mapped[str | None] = mapped_column(Text)
    branche: Mapped[str | None] = mapped_column(String(120))
    extrait_kbis: Mapped[str | None] = mapped_column(String(512))
    cgv_accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    website: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    logo: Mapped[str | None] = mapped_column(String(512))
    vat_rate: Mapped[float | None] = mapped_column("VAT_rate", Numeric(5, 2))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    company_users: Mapped[list["CompanyUser"]] = relationship(
        "CompanyUser", back_populates="company", cascade="all, delete-orphan"
    )
    addresses: Mapped[list["Address"]] = relationship(
        "Address", back_populates="company", cascade="all, delete-orphan"
    )
    products: Mapped[list["Product"]] = relationship(
        "Product", back_populates="company", cascade="all, delete-orphan"
    )
    reviews: Mapped[list["Review"]] = relationship(
        "Review", back_populates="company", cascade="all, delete-orphan"
    )
    shipping_rates: Mapped[list["ShippingRate"]] = relationship(
        "ShippingRate", back_populates="company", cascade="all, delete-orphan"
    )
    bank_infos: Mapped[list["CompanyBankInfo"]] = relationship(
        "CompanyBankInfo", back_populates="company", cascade="all, delete-orphan"
    )
    payment_methods: Mapped[list["CompanyPaymentMethod"]] = relationship(
        "CompanyPaymentMethod", back_populates="company", cascade="all, delete-orphan"
    )
