from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AddressCatalog(Base):
    """Association adresse société ↔ catalogue (origine d'expédition par catalogue)."""

    __tablename__ = "address_catalogs"
    __table_args__ = (
        UniqueConstraint("address_id", "catalog_id", name="uq_address_catalogs_addr_cat"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    address_id: Mapped[int] = mapped_column(
        ForeignKey("addresses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    catalog_id: Mapped[int] = mapped_column(
        ForeignKey("catalogs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    address: Mapped["Address"] = relationship(
        "Address", back_populates="catalog_links"
    )
    catalog: Mapped["Catalog"] = relationship("Catalog")
