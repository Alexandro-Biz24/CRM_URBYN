from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CatalogAttributeDefinition(Base):
    """Attribut obligatoire défini par l'admin pour un catalogue (schéma + défaut)."""

    __tablename__ = "catalog_attribute_definitions"
    __table_args__ = (
        UniqueConstraint(
            "catalog_id",
            "attribute_name",
            name="uq_catalog_attribute_definitions_catalog_name",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    catalog_id: Mapped[int] = mapped_column(
        ForeignKey("catalogs.id", ondelete="CASCADE"),
        nullable=False,
    )
    attribute_name: Mapped[str] = mapped_column(String(120), nullable=False)
    default_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    catalog: Mapped["Catalog"] = relationship(
        "Catalog", back_populates="attribute_definitions"
    )
    mandatory_values: Mapped[list["ProductMandatoryAttributeValue"]] = relationship(
        "ProductMandatoryAttributeValue",
        back_populates="attribute_definition",
        cascade="all, delete-orphan",
    )
