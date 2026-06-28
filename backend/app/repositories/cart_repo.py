from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Cart, CartItem, Company, Product
from app.repositories import product_price_repo


def get_open_cart(db: Session, buyer_id: int) -> Cart | None:
    stmt = (
        select(Cart)
        .options(joinedload(Cart.items).joinedload(CartItem.product))
        .where(Cart.buyer_id == buyer_id, Cart.status == "open")
        .order_by(Cart.updated_at.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def get_or_create_open_cart(db: Session, buyer_id: int, *, currency: str = "EUR") -> Cart:
    cart = get_open_cart(db, buyer_id)
    if cart is not None:
        return cart
    cart = Cart(buyer_id=buyer_id, status="open", currency=currency)
    db.add(cart)
    db.flush()
    return cart


def get_cart_item(db: Session, cart_id: int, item_id: int) -> CartItem | None:
    return db.scalar(
        select(CartItem).where(CartItem.id == item_id, CartItem.cart_id == cart_id)
    )


def get_cart_item_by_product(db: Session, cart_id: int, product_id: int) -> CartItem | None:
    return db.scalar(
        select(CartItem).where(CartItem.cart_id == cart_id, CartItem.product_id == product_id)
    )


def add_or_update_item(
    db: Session,
    *,
    cart: Cart,
    product: Product,
    quantity: int,
) -> CartItem:
    latest = product_price_repo.get_latest_price(db, product.id)
    unit_price = Decimal(str(latest.price)) if latest else Decimal("0")
    currency = latest.currency if latest else cart.currency

    existing = get_cart_item_by_product(db, cart.id, product.id)
    if existing is not None:
        existing.quantity += quantity
        existing.unit_price = unit_price
        existing.currency = currency
        existing.updated_at = datetime.utcnow()
        db.flush()
        return existing

    item = CartItem(
        cart_id=cart.id,
        product_id=product.id,
        seller_company_tva=product.company_tva_intra_com,
        quantity=quantity,
        unit_price=unit_price,
        currency=currency,
    )
    db.add(item)
    cart.updated_at = datetime.utcnow()
    db.flush()
    return item


def update_item_quantity(db: Session, item: CartItem, quantity: int) -> CartItem:
    item.quantity = quantity
    item.updated_at = datetime.utcnow()
    db.flush()
    return item


def delete_item(db: Session, item: CartItem) -> None:
    db.delete(item)
    db.flush()


def load_cart_with_items(db: Session, cart_id: int) -> Cart | None:
    stmt = (
        select(Cart)
        .options(
            joinedload(Cart.items).joinedload(CartItem.product).joinedload(Product.company)
        )
        .where(Cart.id == cart_id)
    )
    return db.scalar(stmt)


def get_company_name(db: Session, tva: str) -> str | None:
    company = db.get(Company, tva)
    return company.company_name if company else None
