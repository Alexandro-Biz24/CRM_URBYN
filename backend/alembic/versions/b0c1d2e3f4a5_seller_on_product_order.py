"""Déplacer seller: orders → product_order (vendeur par ligne).

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-05-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "b0c1d2e3f4a5"
down_revision: Union[str, None] = "a9b0c1d2e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_fk_on_column(table: str, column: str) -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    for fk in insp.get_foreign_keys(table):
        if fk.get("constrained_columns") == [column]:
            op.drop_constraint(fk["name"], table, type_="foreignkey")
            return


def upgrade() -> None:
    op.add_column("product_order", sa.Column("seller", sa.Integer(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE product_order AS po
            SET seller = o.seller
            FROM orders AS o
            WHERE po.order_id = o.id
              AND po.seller IS NULL
            """
        )
    )

    op.alter_column("product_order", "seller", nullable=False)
    op.create_foreign_key(
        "product_order_seller_fkey",
        "product_order",
        "users",
        ["seller"],
        ["id"],
    )
    op.create_index(
        "ix_product_order_order_seller",
        "product_order",
        ["order_id", "seller"],
    )
    op.create_index(
        "ix_product_order_seller",
        "product_order",
        ["seller"],
    )

    _drop_fk_on_column("orders", "seller")
    op.drop_column("orders", "seller")


def downgrade() -> None:
    op.add_column("orders", sa.Column("seller", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "orders_seller_fkey",
        "orders",
        "users",
        ["seller"],
        ["id"],
    )
    op.execute(
        sa.text(
            """
            UPDATE orders AS o
            SET seller = sub.seller
            FROM (
                SELECT DISTINCT ON (order_id) order_id, seller
                FROM product_order
                ORDER BY order_id, id
            ) AS sub
            WHERE o.id = sub.order_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE orders SET seller = buyer WHERE seller IS NULL
            """
        )
    )
    op.alter_column("orders", "seller", nullable=False)

    op.drop_index("ix_product_order_seller", table_name="product_order")
    op.drop_index("ix_product_order_order_seller", table_name="product_order")
    op.drop_constraint("product_order_seller_fkey", "product_order", type_="foreignkey")
    op.drop_column("product_order", "seller")
