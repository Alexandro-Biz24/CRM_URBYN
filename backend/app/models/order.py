from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    buyer_id: Mapped[int] = mapped_column(
        "buyer", ForeignKey("users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    shipping_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    shipping_address_id: Mapped[int | None] = mapped_column(ForeignKey("addresses.id"))
    invoice_address_id: Mapped[int | None] = mapped_column(ForeignKey("addresses.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    buyer_user: Mapped["User"] = relationship(
        "User", foreign_keys=[buyer_id], back_populates="orders_as_buyer"
    )
    items: Mapped[list["ProductOrder"]] = relationship(
        "ProductOrder", back_populates="order", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(
        "Payment", back_populates="order", cascade="all, delete-orphan"
    )
    shipping_address: Mapped["Address | None"] = relationship(
        "Address",
        foreign_keys=[shipping_address_id],
    )
    invoice_address: Mapped["Address | None"] = relationship(
        "Address",
        foreign_keys=[invoice_address_id],
    )
