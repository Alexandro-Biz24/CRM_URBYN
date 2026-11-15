from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OmbragePatioDemande(Base):
    """Demande de chiffrage « solution d'ombrage pour patio » déposée sur le site."""

    __tablename__ = "ombrage_patio_demandes"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    prenom: Mapped[str] = mapped_column(String(80), nullable=False)
    nom: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    telephone: Mapped[str] = mapped_column(String(30), nullable=False)
    societe: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)

    mise_en_place: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Dimensions saisies, puis devis public tel qu'il a été présenté au client.
    patios: Mapped[list] = mapped_column(JSON, nullable=False)
    devis: Mapped[dict] = mapped_column(JSON, nullable=False)

    photos: Mapped[list["OmbragePatioPhoto"]] = relationship(
        back_populates="demande", cascade="all, delete-orphan"
    )


class OmbragePatioPhoto(Base):
    """Photo d'un patio (vue depuis le toit) jointe à une demande, pour simulation."""

    __tablename__ = "ombrage_patio_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    demande_id: Mapped[int] = mapped_column(
        ForeignKey("ombrage_patio_demandes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patio_index: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    demande: Mapped[OmbragePatioDemande] = relationship(back_populates="photos")
