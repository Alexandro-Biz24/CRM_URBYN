from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProductMandatoryAttributeValue(Base):
    """Valeur d'un attribut catalogue obligatoire, saisie pour un produit donné."""

    __tablename__ = "product_mandatory_attribute_values"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "catalog_attribute_definition_id",
            name="uq_product_mandatory_attr_product_definition",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    catalog_attribute_definition_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_attribute_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    value: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    product: Mapped["Product"] = relationship(
        "Product", back_populates="mandatory_attribute_values"
    )
    attribute_definition: Mapped["CatalogAttributeDefinition"] = relationship(
        "CatalogAttributeDefinition", back_populates="mandatory_values"
    )
