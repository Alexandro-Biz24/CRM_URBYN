from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CompanySubscription(Base):
    """Statut d'abonnement fournisseur. Non abonné → prix × urbyn_marge."""

    __tablename__ = "company_subscriptions"

    company_tva_intra_com: Mapped[str] = mapped_column(
        "company_id",
        String(32),
        ForeignKey("companies.tva_intra_com", ondelete="CASCADE"),
        primary_key=True,
    )
    abonne: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    company: Mapped["Company"] = relationship("Company")
