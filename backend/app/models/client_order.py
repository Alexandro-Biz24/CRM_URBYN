from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import JSON

from app.db.base import Base


def _json_type():
    # PostgreSQL → JSONB ; sinon JSON générique (SQLite tests)
    return JSON().with_variant(JSONB(), "postgresql")


class ClientOrder(Base):
    """Demande / commande issue de la validation panier Urbyn (chiffrage)."""

    __tablename__ = "client_orders"
    __table_args__ = (
        Index("ix_client_orders_buyer_created", "buyer_user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    buyer_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="submitted")
    # contact snapshot
    contact_first_name: Mapped[str | None] = mapped_column(String(120))
    contact_last_name: Mapped[str | None] = mapped_column(String(120))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(64))
    # delivery snapshot (JSON)
    delivery_address: Mapped[dict | None] = mapped_column(_json_type(), nullable=True)
    shipping_breakdown: Mapped[dict | list | None] = mapped_column(
        _json_type(), nullable=True
    )
    subtotal_ht: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    shipping_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    install_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total_ht: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total_ttc: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    buyer: Mapped["User"] = relationship("User", foreign_keys=[buyer_user_id])
    items: Mapped[list["ClientOrderItem"]] = relationship(
        "ClientOrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="ClientOrderItem.id",
    )


class ClientOrderItem(Base):
    __tablename__ = "client_order_items"
    __table_args__ = (
        Index("ix_client_order_items_order", "order_id"),
        Index("ix_client_order_items_supplier", "supplier_company_tva"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("client_orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    item_type: Mapped[str] = mapped_column(String(64), nullable=False, default="product")
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price_ht: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    line_total_ht: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    supplier_company_tva: Mapped[str | None] = mapped_column(String(32), nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict | None] = mapped_column(_json_type(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    order: Mapped["ClientOrder"] = relationship("ClientOrder", back_populates="items")
    product: Mapped["Product | None"] = relationship("Product")
