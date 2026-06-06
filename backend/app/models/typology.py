from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Typologie(Base):
    __tablename__ = "typologie"

    id: Mapped[int] = mapped_column(primary_key=True)
    type_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # "user_role" dans la spec → FK vers roles (quel rôle concerne cette typologie)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"))

    role: Mapped["Role | None"] = relationship("Role", back_populates="typologies")
