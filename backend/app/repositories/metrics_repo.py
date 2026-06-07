"""
Métriques : filtre fournisseur via products.companies_id (TVA société).
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import Order, Product, ProductOrder


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def get_internal_totals(db: Session) -> dict:
    total_revenue_stmt: Select[tuple[Decimal]] = select(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).where(Order.status.in_(["paid", "completed", "done"]))
    total_revenue = _to_decimal(db.scalar(total_revenue_stmt))

    total_orders_stmt: Select[tuple[int]] = select(func.count(Order.id))
    total_orders = int(db.scalar(total_orders_stmt) or 0)

    return {
        "total_revenue": total_revenue,
        "total_orders": total_orders,
    }


def get_orders_by_status(db: Session) -> list[tuple[str, int]]:
    rows = db.execute(
        select(Order.status, func.count(Order.id)).group_by(Order.status)
    ).all()
    return [(status, int(count or 0)) for status, count in rows]


def get_monthly_revenue(db: Session) -> list[tuple[date, Decimal]]:
    period_expr = func.date_trunc("month", Order.created_at)
    rows = db.execute(
        select(
            period_expr.label("period"),
            func.coalesce(func.sum(Order.total_amount), 0).label("total"),
        )
        .where(Order.status.in_(["paid", "completed", "done"]))
        .group_by(period_expr)
        .order_by(period_expr)
    ).all()
    return [(p.date() if hasattr(p, "date") else p, _to_decimal(t)) for p, t in rows]


def get_supplier_order_metrics(db: Session, tva_intra_com: str) -> dict:
    tva = tva_intra_com.strip()
    total_revenue_stmt = (
        select(func.coalesce(func.sum(ProductOrder.total_price), 0))
        .join(Product, Product.id == ProductOrder.product_id)
        .where(Product.company_tva_intra_com == tva)
    )
    total_revenue = _to_decimal(db.scalar(total_revenue_stmt))

    orders_count_stmt = (
        select(func.count(func.distinct(ProductOrder.order_id)))
        .join(Product, Product.id == ProductOrder.product_id)
        .where(Product.company_tva_intra_com == tva)
    )
    orders_count = int(db.scalar(orders_count_stmt) or 0)

    period_expr = func.date_trunc("month", Order.created_at)
    rows = (
        db.execute(
            select(
                period_expr.label("period"),
                func.coalesce(func.sum(ProductOrder.total_price), 0).label("total"),
            )
            .join(Order, Order.id == ProductOrder.order_id)
            .join(Product, Product.id == ProductOrder.product_id)
            .where(Product.company_tva_intra_com == tva)
            .group_by(period_expr)
            .order_by(period_expr)
        )
        .all()
    )
    monthly = [(p.date() if hasattr(p, "date") else p, _to_decimal(t)) for p, t in rows]

    return {
        "total_revenue": total_revenue,
        "orders_count": orders_count,
        "monthly_revenue": monthly,
    }


def get_supplier_stock_metrics(db: Session, tva_intra_com: str) -> dict:
    tva = tva_intra_com.strip()
    products_count = int(
        db.scalar(
            select(func.count(Product.id)).where(Product.company_tva_intra_com == tva)
        )
        or 0
    )
    return {
        "products_count": products_count,
        "stock_total": 0,
        "stock_reserved": 0,
    }
