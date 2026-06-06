from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Catalog(Base):
    """Catalogue partagé (arborescence via parent_id)."""

    __tablename__ = "catalogs"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("catalogs.id"))
    name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    parent: Mapped["Catalog | None"] = relationship(
        "Catalog", remote_side="Catalog.id", back_populates="children"
    )
    children: Mapped[list["Catalog"]] = relationship(
        "Catalog", back_populates="parent"
    )
    products: Mapped[list["Product"]] = relationship(
        "Product", back_populates="catalog", foreign_keys="Product.catalog_ref"
    )
    product_orders: Mapped[list["ProductOrder"]] = relationship(
        "ProductOrder", back_populates="catalog"
    )
