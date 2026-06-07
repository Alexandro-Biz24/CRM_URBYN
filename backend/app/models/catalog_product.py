from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CatalogProduct(Base):
    """Association produit ↔ catalogue (N–N)."""

    __tablename__ = "catalog_products"

    catalog_id: Mapped[int] = mapped_column(
        ForeignKey("catalogs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    )

    catalog: Mapped["Catalog"] = relationship("Catalog", back_populates="catalog_products")
    product: Mapped["Product"] = relationship("Product", back_populates="catalog_products")
