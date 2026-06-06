from sqlalchemy.orm import Session

from app.repositories import metrics_repo
from app.schemas.metrics import (
    InternalMetrics,
    OrdersByStatus,
    RevenuePoint,
    SupplierMetrics,
)


def build_internal_metrics(db: Session) -> InternalMetrics:
    totals = metrics_repo.get_internal_totals(db)
    orders_by_status_raw = metrics_repo.get_orders_by_status(db)
    monthly_revenue_raw = metrics_repo.get_monthly_revenue(db)

    orders_by_status = [
        OrdersByStatus(status=status, count=count)
        for status, count in orders_by_status_raw
    ]
    monthly_revenue = [
        RevenuePoint(period=period, total=total)
        for period, total in monthly_revenue_raw
    ]

    return InternalMetrics(
        total_revenue=totals["total_revenue"],
        total_orders=totals["total_orders"],
        orders_by_status=orders_by_status,
        monthly_revenue=monthly_revenue,
    )


def build_supplier_metrics(db: Session, tva_intra_com: str) -> SupplierMetrics:
    order_metrics = metrics_repo.get_supplier_order_metrics(db, tva_intra_com=tva_intra_com)
    stock_metrics = metrics_repo.get_supplier_stock_metrics(db, tva_intra_com=tva_intra_com)

    monthly_revenue = [
        RevenuePoint(period=period, total=total)
        for period, total in order_metrics["monthly_revenue"]
    ]

    return SupplierMetrics(
        tva_intra_com=tva_intra_com.strip(),
        total_revenue=order_metrics["total_revenue"],
        orders_count=order_metrics["orders_count"],
        monthly_revenue=monthly_revenue,
        products_count=stock_metrics["products_count"],
        stock_total=stock_metrics["stock_total"],
        stock_reserved=stock_metrics["stock_reserved"],
    )
