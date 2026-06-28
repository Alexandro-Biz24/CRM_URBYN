from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_sku: Mapped[str] = mapped_column("ADMIN_SKU", String(100), unique=True, nullable=False)
    client_sku: Mapped[str] = mapped_column("Client_sku", String(100), nullable=False)
    company_tva_intra_com: Mapped[str] = mapped_column(
        "companies_id",
        String(32),
        ForeignKey("companies.tva_intra_com"),
        nullable=False,
    )
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    company: Mapped["Company"] = relationship("Company", back_populates="products")
    catalog_products: Mapped[list["CatalogProduct"]] = relationship(
        "CatalogProduct", back_populates="product", cascade="all, delete-orphan"
    )
    translations: Mapped[list["ProductTranslation"]] = relationship(
        "ProductTranslation", back_populates="product", cascade="all, delete-orphan"
    )
    price_history: Mapped[list["ProductPriceHistory"]] = relationship(
        "ProductPriceHistory", back_populates="product", cascade="all, delete-orphan"
    )
    attributes: Mapped[list["ProductAttribut"]] = relationship(
        "ProductAttribut", back_populates="product", cascade="all, delete-orphan"
    )
    mandatory_attribute_values: Mapped[list["ProductMandatoryAttributeValue"]] = (
        relationship(
            "ProductMandatoryAttributeValue",
            back_populates="product",
            cascade="all, delete-orphan",
        )
    )
    product_orders: Mapped[list["ProductOrder"]] = relationship(
        "ProductOrder", back_populates="product"
    )
    cart_items: Mapped[list["CartItem"]] = relationship(
        "CartItem", back_populates="product"
    )
