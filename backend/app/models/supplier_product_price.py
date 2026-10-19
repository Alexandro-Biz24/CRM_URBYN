from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SupplierProductPrice(Base):
    """Offre fournisseur sur un produit (append-only).

    Offre courante = dernière ligne par (company, product) sur `recorded_at`.
    """

    __tablename__ = "supplier_product_prices"
    __table_args__ = (
        Index(
            "ix_spp_product_company_recorded",
            "product_id",
            "company_id",
            "recorded_at",
        ),
        Index("ix_spp_company", "company_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_tva_intra_com: Mapped[str] = mapped_column(
        "company_id",
        String(32),
        ForeignKey("companies.tva_intra_com", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    urbyn_marge: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=1)
    delai_jours: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), default=datetime.utcnow
    )

    company: Mapped["Company"] = relationship("Company")
    product: Mapped["Product"] = relationship("Product")
