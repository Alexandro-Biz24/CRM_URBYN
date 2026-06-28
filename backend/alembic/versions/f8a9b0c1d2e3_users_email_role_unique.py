"""users: unicité composite (email, role_id) au lieu de email seul.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-05-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_unique_on_email_only() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    for uc in insp.get_unique_constraints("users"):
        cols = uc.get("constrained_columns") or []
        if cols == ["email"]:
            op.drop_constraint(uc["name"], "users", type_="unique")
            return
    # Nom auto PostgreSQL courant si inspect ne matche pas
    op.drop_constraint("users_email_key", "users", type_="unique")


def upgrade() -> None:
    _drop_unique_on_email_only()
    op.create_unique_constraint(
        "uq_users_email_role",
        "users",
        ["email", "role_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_users_email_role", "users", type_="unique")
    op.create_unique_constraint("users_email_key", "users", ["email"])
