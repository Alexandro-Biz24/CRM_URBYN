"""Add address.label and products.address_id for labelled company addresses.

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-09-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "addresses",
        sa.Column("label", sa.String(length=120), nullable=True),
    )
    # Backfill : libellé = type existant (ex. « Siège social »)
    op.execute(
        sa.text(
            "UPDATE addresses SET label = type "
            "WHERE label IS NULL AND type IS NOT NULL AND type <> ''"
        )
    )
    op.add_column(
        "products",
        sa.Column("address_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_products_address_id",
        "products",
        "addresses",
        ["address_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_products_address_id", "products", type_="foreignkey")
    op.drop_column("products", "address_id")
    op.drop_column("addresses", "label")
