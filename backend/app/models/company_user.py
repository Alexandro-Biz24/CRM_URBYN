from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CompanyUser(Base):
    """Liaison N-N entre users et companies (plusieurs utilisateurs par société)."""

    __tablename__ = "companies_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    company_tva_intra_com: Mapped[str] = mapped_column(
        "company_id",
        String(32),
        ForeignKey("companies.tva_intra_com"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="company_memberships")
    company: Mapped["Company"] = relationship(
        "Company", back_populates="company_users"
    )
