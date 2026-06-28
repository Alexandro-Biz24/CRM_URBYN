from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    auth,
    client_orders_v2,
    client_portal,
    clients,
    clients_v2,
    metrics,
    supplier_portal,
    supplier_shipping_payment,
    suppliers,
    suppliers_offers_v2,
    suppliers_v2,
)


api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

api_router.include_router(admin.router, prefix="/admin", tags=["admin"])

# Métriques internes & fournisseur (dashboards)
api_router.include_router(metrics.router, prefix="/metrics", tags=["metrics"])

# Gestion des comptes fournisseurs (inscription, futur CRUD, etc.)
api_router.include_router(
    suppliers.router,
    prefix="/suppliers",
    tags=["suppliers"],
)

# V2 fournisseurs (split company existante / nouvelle company)
api_router.include_router(
    suppliers_v2.router,
    prefix="/suppliers/v2",
    tags=["suppliers-v2"],
)
api_router.include_router(
    suppliers_offers_v2.router,
    prefix="/suppliers/v2",
    tags=["suppliers-v2"],
)

# Gestion des comptes client (inscription, futur CRUD, etc.)
api_router.include_router(
    clients.router,
    prefix="/clients",
    tags=["clients"],
)

# V2 client entreprise (split company existante / nouvelle company)
api_router.include_router(
    clients_v2.router,
    prefix="/clients/v2",
    tags=["clients-v2"],
)

api_router.include_router(
    client_orders_v2.router,
    prefix="/clients/v2",
    tags=["clients-orders-v2"],
)

api_router.include_router(
    client_portal.router,
    prefix="/client-portal",
    tags=["client-portal"],
)

api_router.include_router(
    supplier_portal.router,
    prefix="/supplier-portal",
    tags=["supplier-portal"],
)

api_router.include_router(
    supplier_shipping_payment.router,
    prefix="/supplier-portal",
    tags=["supplier-portal"],
)

