from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CatalogLink(Base):
    """Lien directionnel entre deux catalogues (from → to), déclaré par les fournisseurs."""

    __tablename__ = "catalog_links"
    __table_args__ = (
        UniqueConstraint("from_catalog_id", "to_catalog_id", name="uq_catalog_links_from_to"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_catalog_id: Mapped[int] = mapped_column(
        ForeignKey("catalogs.id", ondelete="CASCADE"),
        nullable=False,
    )
    to_catalog_id: Mapped[int] = mapped_column(
        ForeignKey("catalogs.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    from_catalog: Mapped["Catalog"] = relationship(
        "Catalog",
        foreign_keys=[from_catalog_id],
        back_populates="outgoing_links",
    )
    to_catalog: Mapped["Catalog"] = relationship(
        "Catalog",
        foreign_keys=[to_catalog_id],
        back_populates="incoming_links",
    )
