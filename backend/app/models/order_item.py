from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProductOrder(Base):
    __tablename__ = "product_order"
    __table_args__ = (
        Index("ix_product_order_order_seller", "order_id", "seller"),
        Index("ix_product_order_seller", "seller"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    seller_id: Mapped[int] = mapped_column(
        "seller", ForeignKey("users.id"), nullable=False
    )
    catalog_id: Mapped[int] = mapped_column(ForeignKey("catalogs.id"), nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    shipping_cost: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    total_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    order: Mapped["Order"] = relationship("Order", back_populates="items")
    seller_user: Mapped["User"] = relationship(
        "User", foreign_keys=[seller_id], back_populates="product_orders_as_seller"
    )
    catalog: Mapped["Catalog"] = relationship("Catalog", back_populates="product_orders")
    product: Mapped["Product | None"] = relationship(
        "Product", back_populates="product_orders"
    )
