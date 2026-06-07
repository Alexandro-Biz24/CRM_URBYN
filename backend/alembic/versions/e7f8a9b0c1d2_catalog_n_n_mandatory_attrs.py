"""Catalog N-N, catalog_links, attributs obligatoires, products allégés.

Revision ID: e7f8a9b0c1d2
Revises: d1e2f3a4b5c6
Create Date: 2026-05-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRODUCT_COLUMNS_TO_DROP = (
    "quantity",
    "teinte",
    "type_de_produit",
    "gamme",
    "duree_garantie",
    "conditions_garantie",
    "piece_ouvrage_destination",
    "traitement_bois_classification",
    "produit_nuance",
    "description_profil",
    "couleur_traitement_autoclave",
    "code_douane_sh8",
    "type_bois",
    "essence_bois",
    "longueur",
    "largeur",
    "hauteur",
    "volume",
    "poids_net",
)


def _drop_fk_on_column(table: str, column: str) -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    for fk in insp.get_foreign_keys(table):
        if fk.get("constrained_columns") == [column]:
            op.drop_constraint(fk["name"], table, type_="foreignkey")
            return


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    op.create_table(
        "catalog_products",
        sa.Column("catalog_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["catalog_id"], ["catalogs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("catalog_id", "product_id"),
    )

    if _column_exists("products", "catalog_ref"):
        op.execute(
            sa.text(
                """
                INSERT INTO catalog_products (catalog_id, product_id)
                SELECT catalog_ref, id FROM products
                WHERE catalog_ref IS NOT NULL
                ON CONFLICT (catalog_id, product_id) DO NOTHING
                """
            )
        )
        _drop_fk_on_column("products", "catalog_ref")
        op.drop_column("products", "catalog_ref")

    op.create_table(
        "catalog_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("from_catalog_id", sa.Integer(), nullable=False),
        sa.Column("to_catalog_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["from_catalog_id"], ["catalogs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_catalog_id"], ["catalogs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "from_catalog_id", "to_catalog_id", name="uq_catalog_links_from_to"
        ),
    )

    op.create_table(
        "catalog_attribute_definitions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("catalog_id", sa.Integer(), nullable=False),
        sa.Column("attribute_name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["catalog_id"], ["catalogs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "catalog_id",
            "attribute_name",
            name="uq_catalog_attribute_definitions_catalog_name",
        ),
    )

    op.create_table(
        "product_mandatory_attribute_values",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("catalog_attribute_definition_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["catalog_attribute_definition_id"],
            ["catalog_attribute_definitions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_id",
            "catalog_attribute_definition_id",
            name="uq_product_mandatory_attr_product_definition",
        ),
    )

    if _column_exists("products", "product_type"):
        op.alter_column("products", "product_type", new_column_name="product_name")
        op.alter_column(
            "products",
            "product_name",
            existing_type=sa.String(length=32),
            type_=sa.String(length=255),
            existing_nullable=False,
        )

    for col in _PRODUCT_COLUMNS_TO_DROP:
        if _column_exists("products", col):
            op.drop_column("products", col)


def downgrade() -> None:
    raise NotImplementedError(
        "Downgrade non supporté ; restaurer un backup ou git des modèles."
    )
