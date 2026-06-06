from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_sku: Mapped[str] = mapped_column("ADMIN_SKU", String(100), unique=True, nullable=False)
    catalog_ref: Mapped[int] = mapped_column(ForeignKey("catalogs.id"), nullable=False)
    client_sku: Mapped[str] = mapped_column("Client_sku", String(100), nullable=False)
    company_tva_intra_com: Mapped[str] = mapped_column(
        "companies_id",
        String(32),
        ForeignKey("companies.tva_intra_com"),
        nullable=False,
    )
    product_type: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    teinte: Mapped[str | None] = mapped_column(String(120))
    type_de_produit: Mapped[str | None] = mapped_column(String(120))
    gamme: Mapped[str | None] = mapped_column(String(120))
    duree_garantie: Mapped[str | None] = mapped_column(String(64))
    conditions_garantie: Mapped[str | None] = mapped_column(Text)
    piece_ouvrage_destination: Mapped[str | None] = mapped_column(String(255))
    traitement_bois_classification: Mapped[str | None] = mapped_column(String(255))
    produit_nuance: Mapped[str | None] = mapped_column(String(255))
    description_profil: Mapped[str | None] = mapped_column(Text)
    couleur_traitement_autoclave: Mapped[str | None] = mapped_column(String(120))
    code_douane_sh8: Mapped[str | None] = mapped_column(String(20))
    type_bois: Mapped[str | None] = mapped_column(String(120))
    essence_bois: Mapped[str | None] = mapped_column(String(120))
    longueur: Mapped[float | None] = mapped_column(Numeric(12, 3))
    largeur: Mapped[float | None] = mapped_column(Numeric(12, 3))
    hauteur: Mapped[float | None] = mapped_column(Numeric(12, 3))
    volume: Mapped[float | None] = mapped_column(Numeric(12, 5))
    poids_net: Mapped[float | None] = mapped_column(Numeric(12, 3))

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    catalog: Mapped["Catalog"] = relationship(
        "Catalog", back_populates="products", foreign_keys=[catalog_ref]
    )
    company: Mapped["Company"] = relationship("Company", back_populates="products")
    translations: Mapped[list["ProductTranslation"]] = relationship(
        "ProductTranslation", back_populates="product", cascade="all, delete-orphan"
    )
    price_history: Mapped[list["ProductPriceHistory"]] = relationship(
        "ProductPriceHistory", back_populates="product", cascade="all, delete-orphan"
    )
    attributes: Mapped[list["ProductAttribut"]] = relationship(
        "ProductAttribut", back_populates="product", cascade="all, delete-orphan"
    )
    product_orders: Mapped[list["ProductOrder"]] = relationship(
        "ProductOrder", back_populates="product"
    )
