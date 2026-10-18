"""Multi-fournisseur : offres append-only, abonnements, caches géo.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-10-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

URBANIZE_TVA = "FR73827458779"


def upgrade() -> None:
    op.create_table(
        "supplier_product_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.String(length=32),
            sa.ForeignKey("companies.tva_intra_com", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="EUR"),
        sa.Column("urbyn_marge", sa.Numeric(6, 4), nullable=False, server_default="1"),
        sa.Column("delai_jours", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stock", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_spp_product_company_recorded",
        "supplier_product_prices",
        ["product_id", "company_id", "recorded_at"],
    )
    op.create_index("ix_spp_company", "supplier_product_prices", ["company_id"])

    op.create_table(
        "company_subscriptions",
        sa.Column(
            "company_id",
            sa.String(length=32),
            sa.ForeignKey("companies.tva_intra_com", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("abonne", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "geocode_cache",
        sa.Column("query_key", sa.String(length=255), primary_key=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "road_distance_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("origin_key", sa.String(length=255), nullable=False),
        sa.Column("dest_key", sa.String(length=255), nullable=False),
        sa.Column("km", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("origin_key", "dest_key", name="uq_road_distance_origin_dest"),
    )

    op.execute(
        sa.text(
            "INSERT INTO company_subscriptions (company_id, abonne) "
            "SELECT tva_intra_com, false FROM companies WHERE tva_intra_com = :tva "
            "ON CONFLICT (company_id) DO NOTHING"
        ).bindparams(tva=URBANIZE_TVA)
    )


def downgrade() -> None:
    op.drop_table("road_distance_cache")
    op.drop_table("geocode_cache")
    op.drop_table("company_subscriptions")
    op.drop_index("ix_spp_company", table_name="supplier_product_prices")
    op.drop_index("ix_spp_product_company_recorded", table_name="supplier_product_prices")
    op.drop_table("supplier_product_prices")
