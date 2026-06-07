from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import Order, Product, ProductOrder, Role, User, CompanyUser


ROLE_CLIENT = "Client"


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_role_name(db: Session, role_id: int | None) -> str | None:
    if role_id is None:
        return None
    role = db.get(Role, role_id)
    return role.role_name if role else None


def get_company_tva_for_user(db: Session, user_id: int) -> str | None:
    stmt = (
        select(CompanyUser.company_tva_intra_com)
        .where(CompanyUser.user_id == user_id)
        .order_by(CompanyUser.id.desc())
    )
    return db.scalar(stmt)


def get_product(db: Session, product_id: int) -> Product | None:
    return db.get(Product, product_id)


def create_order(
    db: Session,
    *,
    buyer_id: int,
    status: str,
    subtotal: Decimal,
    tax_amount: Decimal,
    shipping_amount: Decimal,
    total_amount: Decimal,
    currency: str,
    shipping_address_id: int | None,
    invoice_address_id: int | None,
) -> Order:
    order = Order(
        seller_id=buyer_id,
        buyer_id=buyer_id,
        status=status,
        subtotal=subtotal,
        tax_amount=tax_amount,
        shipping_amount=shipping_amount,
        total_amount=total_amount,
        currency=currency,
        shipping_address_id=shipping_address_id,
        invoice_address_id=invoice_address_id,
    )
    db.add(order)
    db.flush()
    return order


def create_product_order(
    db: Session,
    *,
    order_id: int,
    catalog_id: int,
    product_id: int,
    quantity: int,
    unit_price: Decimal,
    shipping_cost: Decimal,
    total_price: Decimal,
) -> ProductOrder:
    line = ProductOrder(
        order_id=order_id,
        catalog_id=catalog_id,
        product_id=product_id,
        quantity=quantity,
        unit_price=unit_price,
        shipping_cost=shipping_cost,
        total_price=total_price,
    )
    db.add(line)
    db.flush()
    return line


def decrement_product_stock(db: Session, product: Product, qty: int) -> None:
    """No-op — le stock n'est plus géré sur products (Patch v2)."""
    return
