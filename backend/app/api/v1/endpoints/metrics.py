from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.metrics import InternalMetrics, SupplierMetrics
from app.services.metrics import build_internal_metrics, build_supplier_metrics


router = APIRouter()


@router.get("/internal", response_model=InternalMetrics)
def get_internal_metrics(
    db: Session = Depends(get_db),
) -> InternalMetrics:
    """
    Dashboard **interne** : agrégats globaux (revenu, commandes par statut, série mensuelle).
    Schéma v5 sans tenant.
    """
    return build_internal_metrics(db=db)


@router.get("/supplier", response_model=SupplierMetrics)
def get_supplier_metrics(
    tva_intra_com: str = Query(
        ...,
        description="TVA intracommunautaire (identifiant unique de la société, PK `companies`)",
    ),
    db: Session = Depends(get_db),
) -> SupplierMetrics:
    """
    Dashboard **fournisseur** : revenu, commandes et stock pour une société (`catalog_items.company_id` = cette TVA).
    """
    return build_supplier_metrics(db=db, tva_intra_com=tva_intra_com)
