"""Add front_payload JSON snapshot on carts for Urbyn configurator cart.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-07-31

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        col = sa.Column("front_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    else:
        col = sa.Column("front_payload", sa.JSON(), nullable=True)
    op.add_column("carts", col)


def downgrade() -> None:
    op.drop_column("carts", "front_payload")
