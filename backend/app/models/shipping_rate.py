from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingRate(Base):
    __tablename__ = "shipping_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_tva_intra_com: Mapped[str] = mapped_column(
        "company_id",
        String(32),
        ForeignKey("companies.tva_intra_com"),
        nullable=False,
    )
    carrier_name: Mapped[str | None] = mapped_column(String(100))
    zone_from: Mapped[str | None] = mapped_column(String(64))
    zone_to: Mapped[str | None] = mapped_column(String(64))
    weight_min_kg: Mapped[float | None] = mapped_column(Float)
    weight_max_kg: Mapped[float | None] = mapped_column(Float)
    volume_max_m3: Mapped[float | None] = mapped_column(Float)
    rate_per_kg: Mapped[float | None] = mapped_column(Numeric(12, 4))
    base_rate: Mapped[float | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    company: Mapped["Company"] = relationship("Company", back_populates="shipping_rates")
