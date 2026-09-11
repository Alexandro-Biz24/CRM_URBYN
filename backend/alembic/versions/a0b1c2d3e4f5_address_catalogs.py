"""Add address_catalogs for labelled address ↔ catalog origin mapping.

Revision ID: a0b1c2d3e4f5
Revises: f9a0b1c2d3e4
Create Date: 2026-09-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a0b1c2d3e4f5"
down_revision: Union[str, None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "address_catalogs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("address_id", sa.Integer(), nullable=False),
        sa.Column("catalog_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["address_id"],
            ["addresses.id"],
            name="fk_address_catalogs_address_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["catalog_id"],
            ["catalogs.id"],
            name="fk_address_catalogs_catalog_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "address_id",
            "catalog_id",
            name="uq_address_catalogs_addr_cat",
        ),
    )
    op.create_index(
        "ix_address_catalogs_address_id",
        "address_catalogs",
        ["address_id"],
    )
    op.create_index(
        "ix_address_catalogs_catalog_id",
        "address_catalogs",
        ["catalog_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_address_catalogs_catalog_id", table_name="address_catalogs")
    op.drop_index("ix_address_catalogs_address_id", table_name="address_catalogs")
    op.drop_table("address_catalogs")
