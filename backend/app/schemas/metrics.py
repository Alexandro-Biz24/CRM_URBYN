from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class RevenuePoint(BaseModel):
    period: date = Field(..., description="Début du mois agrégé")
    total: Decimal = Field(..., description="Revenu total pour ce mois")


class OrdersByStatus(BaseModel):
    status: str
    count: int


class InternalMetrics(BaseModel):
    """Dashboard global (schéma v5 sans tenant)."""
    total_revenue: Decimal
    total_orders: int
    orders_by_status: list[OrdersByStatus]
    monthly_revenue: list[RevenuePoint]


class SupplierMetrics(BaseModel):
    """Dashboard fournisseur : métriques pour une société identifiée par sa TVA intracom."""
    tva_intra_com: str
    total_revenue: Decimal
    orders_count: int
    monthly_revenue: list[RevenuePoint]
    products_count: int
    stock_total: int
    stock_reserved: int
