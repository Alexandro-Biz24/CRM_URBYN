"""Offres fournisseurs (append-only) et abonnements."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import CompanySubscription, SupplierProductPrice


def latest_offer(
    db: Session, company_tva: str, product_id: int
) -> SupplierProductPrice | None:
    return db.scalar(
        select(SupplierProductPrice)
        .where(
            SupplierProductPrice.company_tva_intra_com == company_tva,
            SupplierProductPrice.product_id == product_id,
        )
        .order_by(SupplierProductPrice.recorded_at.desc(), SupplierProductPrice.id.desc())
        .limit(1)
    )


def latest_offers_for_company(
    db: Session, company_tva: str
) -> list[SupplierProductPrice]:
    ranked = (
        select(
            SupplierProductPrice.id,
            func.row_number()
            .over(
                partition_by=SupplierProductPrice.product_id,
                order_by=(
                    SupplierProductPrice.recorded_at.desc(),
                    SupplierProductPrice.id.desc(),
                ),
            )
            .label("rn"),
        )
        .where(SupplierProductPrice.company_tva_intra_com == company_tva)
        .subquery()
    )
    return list(
        db.scalars(
            select(SupplierProductPrice)
            .join(ranked, ranked.c.id == SupplierProductPrice.id)
            .where(ranked.c.rn == 1)
            .order_by(SupplierProductPrice.product_id)
        ).all()
    )


def latest_offers_all(db: Session) -> list[SupplierProductPrice]:
    """Offre courante de chaque paire fournisseur / produit."""
    ranked = (
        select(
            SupplierProductPrice.id,
            func.row_number()
            .over(
                partition_by=(
                    SupplierProductPrice.product_id,
                    SupplierProductPrice.company_tva_intra_com,
                ),
                order_by=(
                    SupplierProductPrice.recorded_at.desc(),
                    SupplierProductPrice.id.desc(),
                ),
            )
            .label("rn"),
        )
        .subquery()
    )
    return list(
        db.scalars(
            select(SupplierProductPrice)
            .join(ranked, ranked.c.id == SupplierProductPrice.id)
            .where(ranked.c.rn == 1)
        ).all()
    )


def latest_offers_for_products(
    db: Session, product_ids: list[int]
) -> list[SupplierProductPrice]:
    """Offre courante de chaque fournisseur, pour chaque produit demandé."""
    if not product_ids:
        return []
    ranked = (
        select(
            SupplierProductPrice.id,
            func.row_number()
            .over(
                partition_by=(
                    SupplierProductPrice.product_id,
                    SupplierProductPrice.company_tva_intra_com,
                ),
                order_by=(
                    SupplierProductPrice.recorded_at.desc(),
                    SupplierProductPrice.id.desc(),
                ),
            )
            .label("rn"),
        )
        .where(SupplierProductPrice.product_id.in_(product_ids))
        .subquery()
    )
    return list(
        db.scalars(
            select(SupplierProductPrice)
            .join(ranked, ranked.c.id == SupplierProductPrice.id)
            .where(ranked.c.rn == 1)
        ).all()
    )


def append_offer(
    db: Session,
    *,
    company_tva: str,
    product_id: int,
    price: Decimal,
    urbyn_marge: Decimal,
    delai_jours: int,
    stock: int,
    source: str,
    currency: str = "EUR",
    skip_if_unchanged: bool = True,
) -> bool:
    """Écrit une nouvelle ligne ; False si identique à l'offre courante."""
    if skip_if_unchanged:
        current = latest_offer(db, company_tva, product_id)
        if (
            current is not None
            and Decimal(str(current.price)) == price
            and Decimal(str(current.urbyn_marge)) == urbyn_marge
            and current.delai_jours == delai_jours
            and current.stock == stock
            and current.currency == currency
        ):
            return False
    db.add(
        SupplierProductPrice(
            company_tva_intra_com=company_tva,
            product_id=product_id,
            price=price,
            currency=currency,
            urbyn_marge=urbyn_marge,
            delai_jours=delai_jours,
            stock=stock,
            source=source,
            recorded_at=datetime.utcnow(),
        )
    )
    return True


def delete_offers_for_product(db: Session, company_tva: str, product_id: int) -> int:
    """Retire toutes les offres d'un fournisseur sur un produit."""
    result = db.execute(
        delete(SupplierProductPrice).where(
            SupplierProductPrice.company_tva_intra_com == company_tva,
            SupplierProductPrice.product_id == product_id,
        )
    )
    return int(result.rowcount or 0)


def delete_offers_for_companies(db: Session, company_tvas: list[str]) -> int:
    if not company_tvas:
        return 0
    result = db.execute(
        delete(SupplierProductPrice).where(
            SupplierProductPrice.company_tva_intra_com.in_(company_tvas)
        )
    )
    return int(result.rowcount or 0)


def get_subscription(db: Session, company_tva: str) -> CompanySubscription | None:
    return db.get(CompanySubscription, company_tva)


def subscription_map(db: Session) -> dict[str, bool]:
    return {
        row.company_tva_intra_com: bool(row.abonne)
        for row in db.scalars(select(CompanySubscription)).all()
    }


def set_subscription(db: Session, company_tva: str, abonne: bool) -> bool:
    """Upsert ; True si la ligne a été créée."""
    current = get_subscription(db, company_tva)
    if current is None:
        db.add(
            CompanySubscription(
                company_tva_intra_com=company_tva,
                abonne=abonne,
                updated_at=datetime.utcnow(),
            )
        )
        return True
    if current.abonne != abonne:
        current.abonne = abonne
        current.updated_at = datetime.utcnow()
    return False


def clear_subscriptions(db: Session) -> int:
    result = db.execute(delete(CompanySubscription))
    return int(result.rowcount or 0)
