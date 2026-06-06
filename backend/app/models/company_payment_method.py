from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CompanyPaymentMethod(Base):
    __tablename__ = "company_payment_methods"

    id: Mapped[int] = mapped_column(primary_key=True)
    methode: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    company_tva_intra_com: Mapped[str] = mapped_column(
        "company_id",
        String(32),
        ForeignKey("companies.tva_intra_com"),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="company_payment_methods")
    company: Mapped["Company"] = relationship(
        "Company", back_populates="payment_methods"
    )
    bank_info: Mapped["CompanyBankInfo | None"] = relationship(
        "CompanyBankInfo",
        back_populates="payment_method",
        uselist=False,
        foreign_keys="CompanyBankInfo.company_payment_method_id",
        cascade="all, delete-orphan",
    )
