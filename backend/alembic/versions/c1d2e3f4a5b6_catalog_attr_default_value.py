"""Add default_value on catalog_attribute_definitions + backfill support.

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-07-31

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "b0c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "catalog_attribute_definitions",
        sa.Column(
            "default_value",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )
    # Préremplit le défaut avec une valeur produit existante si disponible
    op.execute(
        sa.text(
            """
            UPDATE catalog_attribute_definitions AS d
            SET default_value = COALESCE(
                (
                    SELECT v.value
                    FROM product_mandatory_attribute_values AS v
                    WHERE v.catalog_attribute_definition_id = d.id
                      AND v.value IS NOT NULL
                      AND BTRIM(v.value) <> ''
                    ORDER BY v.id
                    LIMIT 1
                ),
                '0'
            )
            WHERE BTRIM(d.default_value) = ''
            """
        )
    )


def downgrade() -> None:
    op.drop_column("catalog_attribute_definitions", "default_value")
