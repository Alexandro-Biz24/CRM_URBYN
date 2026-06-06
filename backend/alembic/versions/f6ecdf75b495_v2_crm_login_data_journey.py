"""V2 CRM login data journey

Révision corrigée : ordre des opérations + migration int → TVA sur company_id.

Problème d’origine : CREATE TABLE … REFERENCES companies(tva_intra_com) **avant**
que la colonne `tva_intra_com` existe sur `companies`, et ALTER des enfants vers `tva_intra_com`
également **avant** sa création.

Revision ID: f6ecdf75b495
Revises: c9aff6b57f35
Create Date: 2026-03-22 18:22:10.959804

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6ecdf75b495"
down_revision: Union[str, None] = "c9aff6b57f35"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_fk_to_table(table: str, referred_table: str) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for fk in insp.get_foreign_keys(table):
        if fk["referred_table"] == referred_table:
            op.drop_constraint(fk["name"], table, type_="foreignkey")
            return


def _migrate_company_fk_child(table: str, col: str = "company_id") -> None:
    """Remplace company_id INTEGER par VARCHAR(32) = companies.tva_intra_com."""
    tmp = f"{col}_new"
    _drop_fk_to_table(table, "companies")
    op.add_column(table, sa.Column(tmp, sa.String(length=32), nullable=True))
    op.execute(
        sa.text(
            f"""
            UPDATE {table} AS t
            SET {tmp} = c.tva_intra_com
            FROM companies AS c
            WHERE t.{col} = c.id
            """
        )
    )
    op.drop_column(table, col)
    op.execute(
        sa.text(f'ALTER TABLE "{table}" RENAME COLUMN "{tmp}" TO "{col}"')
    )
    op.alter_column(table, col, existing_type=sa.String(length=32), nullable=False)


def upgrade() -> None:
    # --- 1. Tables sans dépendance vers companies.tva_intra_com ---
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("role_name", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_name"),
    )
    op.create_table(
        "typologie",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("type_name", sa.String(length=255), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column(
        "user_profiles", sa.Column("title", sa.String(length=32), nullable=True)
    )
    op.add_column("users", sa.Column("role_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("mobile_phone", sa.String(length=40), nullable=True))
    op.add_column("users", sa.Column("fixe_phone", sa.String(length=40), nullable=True))
    op.create_foreign_key(None, "users", "roles", ["role_id"], ["id"])
    op.drop_column("users", "phone")
    op.drop_column("users", "is_vendor")

    # --- 2. Enrichir companies + colonne tva_intra_com (avant toute FK vers elle) ---
    op.add_column(
        "companies", sa.Column("tva_intra_com", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "companies", sa.Column("company_name", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "companies", sa.Column("phone_number", sa.String(length=40), nullable=True)
    )
    op.add_column(
        "companies", sa.Column("code_naf", sa.String(length=10), nullable=True)
    )
    op.add_column(
        "companies", sa.Column("email", sa.String(length=320), nullable=True)
    )
    op.add_column(
        "companies",
        sa.Column("condition_reglement", sa.Text(), nullable=True),
    )
    op.add_column(
        "companies", sa.Column("branche", sa.String(length=120), nullable=True)
    )
    op.add_column(
        "companies",
        sa.Column("extrait_kbis", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "companies",
        sa.Column(
            "cgv_accepted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "companies", sa.Column("website", sa.String(length=512), nullable=True)
    )
    op.add_column("companies", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "companies", sa.Column("logo", sa.String(length=512), nullable=True)
    )

    # Remplir tva_intra_com et company_name à partir des anciennes colonnes
    op.execute(
        sa.text(
            """
            UPDATE companies
            SET
              tva_intra_com = COALESCE(
                NULLIF(trim(vat_number), ''),
                'LEGACY-' || id::text
              ),
              company_name = COALESCE(
                NULLIF(trim(role), ''),
                'Sans nom'
              )
            WHERE tva_intra_com IS NULL OR company_name IS NULL
            """
        )
    )

    op.alter_column("companies", "tva_intra_com", nullable=False)
    op.alter_column("companies", "company_name", nullable=False)
    op.alter_column(
        "companies",
        "cgv_accepted",
        server_default=None,
    )

    # --- 3. Migrer les tables filles : company_id int → string (TVA) ---
    for tbl in (
        "addresses",
        "catalog_items",
        "catalogs",
        "company_translations",
        "services",
        "shipping_rates",
    ):
        _migrate_company_fk_child(tbl, "company_id")

    # --- 4. Remplacer la PK de companies (id → tva_intra_com) ---
    _drop_fk_to_table("companies", "users")
    bind = op.get_bind()
    insp = sa.inspect(bind)
    pk = insp.get_pk_constraint("companies")
    pk_name = pk.get("name") or "companies_pkey"
    op.drop_constraint(pk_name, "companies", type_="primary")
    op.drop_column("companies", "id")
    op.drop_column("companies", "registration_number")
    op.drop_column("companies", "role")
    op.drop_column("companies", "vat_number")
    op.drop_column("companies", "user_id")
    op.create_primary_key("companies_pkey", "companies", ["tva_intra_com"])

    # --- 5. Recréer les FK enfants → companies(tva_intra_com) ---
    op.create_foreign_key(
        None, "addresses", "companies", ["company_id"], ["tva_intra_com"]
    )
    op.create_foreign_key(
        None, "catalog_items", "companies", ["company_id"], ["tva_intra_com"]
    )
    op.create_foreign_key(
        None, "catalogs", "companies", ["company_id"], ["tva_intra_com"]
    )
    op.create_foreign_key(
        None,
        "company_translations",
        "companies",
        ["company_id"],
        ["tva_intra_com"],
    )
    op.create_foreign_key(
        None, "services", "companies", ["company_id"], ["tva_intra_com"]
    )
    op.create_foreign_key(
        None, "shipping_rates", "companies", ["company_id"], ["tva_intra_com"]
    )

    # --- 6. Nouvelles tables (FK vers tva_intra_com OK) ---
    # Éviter la circularité bank_info ↔ payment_method : payment_methods d’abord sans lien bank
    op.create_table(
        "company_payment_methods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("methode", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.tva_intra_com"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "companies_bank_info",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.String(length=32), nullable=False),
        sa.Column("iban_number", sa.String(length=34), nullable=True),
        sa.Column("bic", sa.String(length=11), nullable=True),
        sa.Column("bank_name", sa.String(length=255), nullable=True),
        sa.Column("iban_proof", sa.String(length=512), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("company_payment_method_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.tva_intra_com"]),
        sa.ForeignKeyConstraint(
            ["company_payment_method_id"], ["company_payment_methods.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column(
        "company_payment_methods",
        sa.Column("companies_bank_info_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        None,
        "company_payment_methods",
        "companies_bank_info",
        ["companies_bank_info_id"],
        ["id"],
    )

    op.create_table(
        "companies_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.tva_intra_com"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- 7. Colonnes adresses (spec DEMANDE) ---
    op.add_column("addresses", sa.Column("siret", sa.String(length=14), nullable=True))
    op.add_column(
        "addresses", sa.Column("intra_communal", sa.String(length=32), nullable=True)
    )


def downgrade() -> None:
    """Inverse partiel : préférer un backup avant upgrade si rollback nécessaire."""
    op.drop_column("addresses", "intra_communal")
    op.drop_column("addresses", "siret")

    op.drop_table("companies_users")
    op.drop_constraint(None, "company_payment_methods", type_="foreignkey")
    op.drop_column("company_payment_methods", "companies_bank_info_id")
    op.drop_table("companies_bank_info")
    op.drop_table("company_payment_methods")

    for tbl in (
        "shipping_rates",
        "services",
        "company_translations",
        "catalogs",
        "catalog_items",
        "addresses",
    ):
        _drop_fk_to_table(tbl, "companies")

    bind = op.get_bind()
    insp = sa.inspect(bind)
    pk = insp.get_pk_constraint("companies")
    pk_name = pk.get("name") or "companies_pkey"
    op.drop_constraint(pk_name, "companies", type_="primary")

    # La suite (recréer id SERIAL, réinjecter company_id int) est hors scope ici.
    raise NotImplementedError(
        "Downgrade incomplet : restaurer manuellement companies.id et les FK int si besoin."
    )
