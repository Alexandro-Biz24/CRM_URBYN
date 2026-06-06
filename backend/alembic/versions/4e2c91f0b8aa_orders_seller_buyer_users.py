"""orders: seller et buyer (FK users), remplace user_id

Revision ID: 4e2c91f0b8aa
Revises: 387f8b01769a
Create Date: 2026-04-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "4e2c91f0b8aa"
down_revision: Union[str, None] = "724835dc71eb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("seller", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("buyer", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "orders_seller_fkey", "orders", "users", ["seller"], ["id"]
    )
    op.create_foreign_key(
        "orders_buyer_fkey", "orders", "users", ["buyer"], ["id"]
    )
    op.execute(sa.text("UPDATE orders SET seller = user_id, buyer = user_id"))
    op.alter_column("orders", "seller", existing_type=sa.Integer(), nullable=False)
    op.alter_column("orders", "buyer", existing_type=sa.Integer(), nullable=False)

    bind = op.get_bind()
    insp = inspect(bind)
    for fk in insp.get_foreign_keys("orders"):
        if fk.get("referred_table") == "users" and fk.get("constrained_columns") == [
            "user_id"
        ]:
            op.drop_constraint(fk["name"], "orders", type_="foreignkey")
            break
    op.drop_column("orders", "user_id")


def downgrade() -> None:
    op.add_column("orders", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(None, "orders", "users", ["user_id"], ["id"])
    op.execute(sa.text("UPDATE orders SET user_id = buyer"))
    op.alter_column("orders", "user_id", existing_type=sa.Integer(), nullable=False)
    op.drop_constraint("orders_seller_fkey", "orders", type_="foreignkey")
    op.drop_constraint("orders_buyer_fkey", "orders", type_="foreignkey")
    op.drop_column("orders", "seller")
    op.drop_column("orders", "buyer")
