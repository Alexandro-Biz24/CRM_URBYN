"""Lien unidirectionnel: companies_bank_info -> company_payment_methods

Revision ID: c4e5f6a7b8c9
Revises: b2c3d4e5f6a7
Create Date: 2026-05-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "c4e5f6a7b8c9"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
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
    op.execute(
        sa.text(
            """
            UPDATE companies_bank_info AS c
            SET company_payment_method_id = pm.id
            FROM company_payment_methods AS pm
            WHERE pm.companies_bank_info_id = c.id
              AND c.company_payment_method_id IS NULL
            """
        )
    )

    _drop_fk_on_column("company_payment_methods", "companies_bank_info_id")
    op.drop_column("company_payment_methods", "companies_bank_info_id")

    _drop_fk_on_column("companies_bank_info", "company_payment_method_id")
    op.create_foreign_key(
        "companies_bank_info_company_payment_method_id_fkey",
        "companies_bank_info",
        "company_payment_methods",
        ["company_payment_method_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_companies_bank_info_payment_method",
        "companies_bank_info",
        ["company_payment_method_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_companies_bank_info_payment_method",
        "companies_bank_info",
        type_="unique",
    )
    op.drop_constraint(
        "companies_bank_info_company_payment_method_id_fkey",
        "companies_bank_info",
        type_="foreignkey",
    )
    op.create_foreign_key(
        None,
        "companies_bank_info",
        "company_payment_methods",
        ["company_payment_method_id"],
        ["id"],
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
    op.execute(
        sa.text(
            """
            UPDATE company_payment_methods AS pm
            SET companies_bank_info_id = c.id
            FROM companies_bank_info AS c
            WHERE c.company_payment_method_id = pm.id
            """
        )
    )
