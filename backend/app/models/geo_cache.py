from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GeocodeCache(Base):
    """Géocodage geo.api.gouv (clé normalisée CP / ville / pays)."""

    __tablename__ = "geocode_cache"

    query_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


class RoadDistanceCache(Base):
    """Distance routière entre deux points géocodés (OSRM, sinon haversine × 1,3)."""

    __tablename__ = "road_distance_cache"
    __table_args__ = (
        UniqueConstraint("origin_key", "dest_key", name="uq_road_distance_origin_dest"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    origin_key: Mapped[str] = mapped_column(String(255), nullable=False)
    dest_key: Mapped[str] = mapped_column(String(255), nullable=False)
    km: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
