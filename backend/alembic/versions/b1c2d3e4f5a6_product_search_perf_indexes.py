"""Indexes for product search performance (attrs + catalog links).

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-09-13
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a0b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Lookups product_id → free attributes (massif/totem N+1 path)
    op.create_index(
        "ix_product_attribut_product_id",
        "product_attribut",
        ["product_id"],
        unique=False,
    )
    # Reverse catalog membership (origin zip / product→catalogs)
    op.create_index(
        "ix_catalog_products_product_id",
        "catalog_products",
        ["product_id"],
        unique=False,
    )
    # Tree navigation (leaf collection)
    op.create_index(
        "ix_catalogs_parent_id_is_active",
        "catalogs",
        ["parent_id", "is_active"],
        unique=False,
    )
    # Active product listing / search
    op.create_index(
        "ix_products_is_active_product_name",
        "products",
        ["is_active", "product_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_products_is_active_product_name", table_name="products")
    op.drop_index("ix_catalogs_parent_id_is_active", table_name="catalogs")
    op.drop_index("ix_catalog_products_product_id", table_name="catalog_products")
    op.drop_index("ix_product_attribut_product_id", table_name="product_attribut")
