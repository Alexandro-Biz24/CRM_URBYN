from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    company_tva_intra_com: Mapped[str] = mapped_column(
        "company_id",
        String(32),
        ForeignKey("companies.tva_intra_com"),
        nullable=False,
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)  # ex. company
    is_verified_purchase: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="reviews")
    company: Mapped["Company"] = relationship("Company", back_populates="reviews")
    translations: Mapped[list["ReviewTranslation"]] = relationship(
        "ReviewTranslation", back_populates="review", cascade="all, delete-orphan"
    )
