from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Role(Base):
    """Rôles applicatifs : Fournisseur, client, admin."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    role_name: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    users: Mapped[list["User"]] = relationship("User", back_populates="role")
    typologies: Mapped[list["Typologie"]] = relationship(
        "Typologie", back_populates="role"
    )
