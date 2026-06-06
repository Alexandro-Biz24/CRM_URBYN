from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CompanyBankInfo(Base):
    __tablename__ = "companies_bank_info"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_tva_intra_com: Mapped[str] = mapped_column(
        "company_id",
        String(32),
        ForeignKey("companies.tva_intra_com"),
        nullable=False,
    )
    iban_number: Mapped[str | None] = mapped_column(String(34))
    bic: Mapped[str | None] = mapped_column(String(11))
    bank_name: Mapped[str | None] = mapped_column(String(255))
    iban_proof: Mapped[str | None] = mapped_column(String(512))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    company_payment_method_id: Mapped[int | None] = mapped_column(
        ForeignKey("company_payment_methods.id", ondelete="CASCADE"),
        unique=True,
    )

    company: Mapped["Company"] = relationship("Company", back_populates="bank_infos")
    payment_method: Mapped["CompanyPaymentMethod | None"] = relationship(
        "CompanyPaymentMethod",
        back_populates="bank_info",
        foreign_keys=[company_payment_method_id],
    )
