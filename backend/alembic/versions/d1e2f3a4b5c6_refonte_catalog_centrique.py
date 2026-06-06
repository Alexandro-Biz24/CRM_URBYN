"""Refonte DB : catalogues centraux, produits liés au catalog, suppression services/items.

Revision ID: d1e2f3a4b5c6
Revises: c4e5f6a7b8c9
Create Date: 2026-05-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "c4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_fk_on_column(table: str, column: str) -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    for fk in insp.get_foreign_keys(table):
        if fk.get("constrained_columns") == [column]:
            op.drop_constraint(fk["name"], table, type_="foreignkey")
            return


def _drop_unique_if_exists(table: str, name: str) -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if name in {uc["name"] for uc in insp.get_unique_constraints(table)}:
        op.drop_constraint(name, table, type_="unique")


def upgrade() -> None:
    # Données sample : on vide les tables impactées avant restructuration.
    op.execute(sa.text("DELETE FROM product_order"))
    op.execute(sa.text("DELETE FROM product_price_history"))
    op.execute(sa.text("DELETE FROM product_translations"))
    op.execute(sa.text("DELETE FROM product_attribut"))
    op.execute(sa.text("DELETE FROM products"))
    op.execute(sa.text("DELETE FROM company_catalog_items"))
    op.execute(sa.text("DELETE FROM catalog_items"))
    op.execute(sa.text("DELETE FROM service_translations"))
    op.execute(sa.text("DELETE FROM services"))

    # --- product_order ---
    _drop_fk_on_column("product_order", "service_id")
    op.drop_column("product_order", "service_id")
    op.drop_column("product_order", "item_type")
    op.add_column(
        "product_order",
        sa.Column("catalog_id", sa.Integer(), nullable=False),
    )
    op.create_foreign_key(
        "product_order_catalog_id_fkey",
        "product_order",
        "catalogs",
        ["catalog_id"],
        ["id"],
    )

    if _column_exists("catalogs", "company_id"):
        op.execute(
            sa.text(
                """
                INSERT INTO catalogs (
                    company_id, name, description, is_active, created_at, updated_at, parent_id
                )
                SELECT
                    (SELECT tva_intra_com FROM companies ORDER BY tva_intra_com LIMIT 1),
                    'Catalogue racine',
                    'Créé par migration refonte',
                    true,
                    NOW(),
                    NOW(),
                    NULL
                WHERE NOT EXISTS (SELECT 1 FROM catalogs)
                  AND EXISTS (SELECT 1 FROM companies)
                """
            )
        )
    else:
        op.execute(
            sa.text(
                """
                INSERT INTO catalogs (name, description, is_active, created_at, updated_at, parent_id)
                SELECT 'Catalogue racine', 'Créé par migration refonte', true, NOW(), NOW(), NULL
                WHERE NOT EXISTS (SELECT 1 FROM catalogs)
                """
            )
        )

    # --- catalogs : retrait company_id ---
    _drop_fk_on_column("catalogs", "company_id")
    op.drop_column("catalogs", "company_id")

    # --- products ---
    _drop_fk_on_column("products", "catalog_item_id")
    _drop_unique_if_exists("products", "products_catalog_item_id_key")
    _drop_unique_if_exists("products", "uq_products_company_sku")
    op.drop_column("products", "catalog_item_id")
    op.drop_column("products", "reference_price")
    op.drop_column("products", "currency")

    op.add_column(
        "products",
        sa.Column("ADMIN_SKU", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("catalog_ref", sa.Integer(), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("quantity", sa.Integer(), server_default="0", nullable=False),
    )
    op.alter_column("products", "sku", new_column_name="Client_sku")

    op.execute(
        sa.text(
            """
            UPDATE catalogs SET parent_id = id WHERE parent_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE products
            SET catalog_ref = (SELECT MIN(id) FROM catalogs),
                "ADMIN_SKU" = 'MIG-' || id::text
            WHERE catalog_ref IS NULL
            """
        )
    )

    op.alter_column("products", "ADMIN_SKU", nullable=False)
    op.alter_column("products", "catalog_ref", nullable=False)
    op.create_foreign_key(
        "products_catalog_ref_fkey",
        "products",
        "catalogs",
        ["catalog_ref"],
        ["id"],
    )
    op.create_unique_constraint("uq_products_admin_sku", "products", ["ADMIN_SKU"])

    # --- product_price_history (time series) ---
    op.add_column(
        "product_price_history",
        sa.Column("recorded_at", sa.DateTime(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE product_price_history
            SET recorded_at = COALESCE(effective_at, created_at, NOW())
            """
        )
    )
    op.alter_column("product_price_history", "recorded_at", nullable=False)
    if _column_exists("product_price_history", "effective_at"):
        op.drop_column("product_price_history", "effective_at")
    op.create_index(
        "ix_pph_product_recorded_at",
        "product_price_history",
        ["product_id", "recorded_at"],
    )

    op.drop_table("company_catalog_items")
    op.drop_table("catalog_items")
    op.drop_table("service_translations")
    op.drop_table("services")


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def downgrade() -> None:
    raise NotImplementedError(
        "Downgrade refonte catalog centrique non supporté ; restaurer un backup Neon ou git des modèles."
    )
