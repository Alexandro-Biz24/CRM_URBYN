"""Solutions d'ombrage : demandes de chiffrage patio et photos jointes.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-11-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ombrage_patio_demandes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("prenom", sa.String(length=80), nullable=False),
        sa.Column("nom", sa.String(length=80), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("telephone", sa.String(length=30), nullable=False),
        sa.Column("societe", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("mise_en_place", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("patios", sa.JSON(), nullable=False),
        sa.Column("devis", sa.JSON(), nullable=False),
    )
    op.create_table(
        "ombrage_patio_photos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "demande_id",
            sa.Integer(),
            sa.ForeignKey("ombrage_patio_demandes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("patio_index", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
    )
    op.create_index(
        "ix_ombrage_patio_photos_demande_id", "ombrage_patio_photos", ["demande_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_ombrage_patio_photos_demande_id", table_name="ombrage_patio_photos")
    op.drop_table("ombrage_patio_photos")
    op.drop_table("ombrage_patio_demandes")
