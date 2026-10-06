from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import ProductPriceHistory


def append_price(
    db: Session,
    *,
    product_id: int,
    price: float | Decimal,
    currency: str,
    recorded_at: datetime | None = None,
) -> ProductPriceHistory:
    row = ProductPriceHistory(
        product_id=product_id,
        recorded_at=recorded_at or datetime.utcnow(),
        price=Decimal(str(price)),
        currency=currency.upper()[:3],
    )
    db.add(row)
    db.flush()
    return row


def get_latest_price(
    db: Session, product_id: int
) -> ProductPriceHistory | None:
    stmt: Select[tuple[ProductPriceHistory]] = (
        select(ProductPriceHistory)
        .where(ProductPriceHistory.product_id == product_id)
        .order_by(ProductPriceHistory.recorded_at.desc(), ProductPriceHistory.id.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def get_latest_prices_for_products(
    db: Session, product_ids: list[int]
) -> dict[int, ProductPriceHistory]:
    """Dernier prix par product_id en une seule requête (PostgreSQL DISTINCT ON)."""
    ids = sorted({int(pid) for pid in product_ids if pid})
    if not ids:
        return {}
    stmt = (
        select(ProductPriceHistory)
        .where(ProductPriceHistory.product_id.in_(ids))
        .distinct(ProductPriceHistory.product_id)
        .order_by(
            ProductPriceHistory.product_id,
            ProductPriceHistory.recorded_at.desc(),
            ProductPriceHistory.id.desc(),
        )
    )
    return {row.product_id: row for row in db.scalars(stmt).all()}
