"""Client orders (Urbyn quote/request history) + purpose on verification codes.

Revision ID: e8f9a0b1c2d3
Revises: d2e3f4a5b6c7
Create Date: 2026-09-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_col(name: str, nullable: bool = True):
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return sa.Column(name, postgresql.JSONB(astext_type=sa.Text()), nullable=nullable)
    return sa.Column(name, sa.JSON(), nullable=nullable)


def upgrade() -> None:
    op.add_column(
        "email_verification_codes",
        sa.Column("purpose", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "email_verification_codes",
        sa.Column("payload", sa.String(length=512), nullable=True),
    )

    op.create_table(
        "client_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("buyer_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="submitted"),
        sa.Column("contact_first_name", sa.String(length=120), nullable=True),
        sa.Column("contact_last_name", sa.String(length=120), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=64), nullable=True),
        _json_col("delivery_address"),
        _json_col("shipping_breakdown"),
        sa.Column("subtotal_ht", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("shipping_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("install_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_ht", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_ttc", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="EUR"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "ix_client_orders_buyer_created",
        "client_orders",
        ["buyer_user_id", "created_at"],
    )

    op.create_table(
        "client_order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("client_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("item_type", sa.String(length=64), nullable=False, server_default="product"),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price_ht", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("line_total_ht", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("supplier_company_tva", sa.String(length=32), nullable=True),
        sa.Column("supplier_name", sa.String(length=255), nullable=True),
        _json_col("details"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_client_order_items_order", "client_order_items", ["order_id"])
    op.create_index(
        "ix_client_order_items_supplier",
        "client_order_items",
        ["supplier_company_tva"],
    )


def downgrade() -> None:
    op.drop_index("ix_client_order_items_supplier", table_name="client_order_items")
    op.drop_index("ix_client_order_items_order", table_name="client_order_items")
    op.drop_table("client_order_items")
    op.drop_index("ix_client_orders_buyer_created", table_name="client_orders")
    op.drop_table("client_orders")
    op.drop_column("email_verification_codes", "payload")
    op.drop_column("email_verification_codes", "purpose")
