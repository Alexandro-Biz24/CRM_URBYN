"""Demandes ombrage patio : adresse du chantier et durée de mise à disposition.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-11-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ombrage_patio_demandes",
        sa.Column("chantier_adresse", sa.String(length=200), nullable=False, server_default=""),
    )
    op.add_column(
        "ombrage_patio_demandes",
        sa.Column("chantier_complement", sa.String(length=200), nullable=False, server_default=""),
    )
    op.add_column(
        "ombrage_patio_demandes",
        sa.Column("chantier_code_postal", sa.String(length=12), nullable=False, server_default=""),
    )
    op.add_column(
        "ombrage_patio_demandes",
        sa.Column("chantier_ville", sa.String(length=80), nullable=False, server_default=""),
    )
    op.add_column(
        "ombrage_patio_demandes",
        sa.Column("chantier_pays", sa.String(length=60), nullable=False, server_default="France"),
    )
    op.add_column(
        "ombrage_patio_demandes",
        sa.Column("duree_annees", sa.Integer(), nullable=False, server_default="5"),
    )


def downgrade() -> None:
    op.drop_column("ombrage_patio_demandes", "duree_annees")
    op.drop_column("ombrage_patio_demandes", "chantier_pays")
    op.drop_column("ombrage_patio_demandes", "chantier_ville")
    op.drop_column("ombrage_patio_demandes", "chantier_code_postal")
    op.drop_column("ombrage_patio_demandes", "chantier_complement")
    op.drop_column("ombrage_patio_demandes", "chantier_adresse")
