"""Plusieurs produits par liaison catalogue ; SKU unique par société.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    unique_names = {
        uc["name"]
        for uc in inspector.get_unique_constraints("products")
    }
    if "products_catalog_item_id_key" in unique_names:
        op.drop_constraint("products_catalog_item_id_key", "products", type_="unique")

    # Rendre les SKU uniques par société avant la contrainte (données existantes)
    op.execute(
        """
        UPDATE products AS p
        SET sku = p.sku || '-dup-' || p.id::text
        WHERE p.id NOT IN (
            SELECT MIN(p2.id)
            FROM products AS p2
            GROUP BY p2.companies_id, lower(trim(p2.sku))
        )
        """
    )

    if "uq_products_company_sku" not in unique_names:
        op.create_unique_constraint(
            "uq_products_company_sku",
            "products",
            ["companies_id", "sku"],
        )


def downgrade() -> None:
    op.drop_constraint("uq_products_company_sku", "products", type_="unique")
    op.create_unique_constraint(
        "products_catalog_item_id_key",
        "products",
        ["catalog_item_id"],
    )
