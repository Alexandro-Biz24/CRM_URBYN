from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Address,
    Cart,
    CartItem,
    CatalogProduct,
    Company,
    CompanyBankInfo,
    CompanyPaymentMethod,
    CompanyUser,
    EmailVerificationCode,
    Order,
    Payment,
    Product,
    ProductAttribut,
    ProductMandatoryAttributeValue,
    ProductOrder,
    ProductPriceHistory,
    ProductTranslation,
    Review,
    ReviewTranslation,
    Role,
    ShippingRate,
    User,
    UserProfile,
)

ROLE_SUPPLIER = "Fournisseur"
ROLE_CLIENT = "Client"


def _dt_iso(dt) -> str:
    return dt.isoformat() if dt else ""


def _user_list_item(user: User, company: Company | None) -> dict:
    profile = user.profile
    return {
        "id": user.id,
        "email": user.email,
        "first_name": profile.first_name if profile else None,
        "last_name": profile.last_name if profile else None,
        "company_name": company.company_name if company else None,
        "company_tva": company.tva_intra_com if company else None,
        "is_active": user.is_active,
        "email_verified": user.email_verified,
        "created_at": _dt_iso(user.created_at),
    }


def _latest_company_for_user(db: Session, user_id: int) -> Company | None:
    stmt = (
        select(Company)
        .join(CompanyUser, CompanyUser.company_tva_intra_com == Company.tva_intra_com)
        .where(CompanyUser.user_id == user_id)
        .order_by(CompanyUser.id.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def list_users_by_role(db: Session) -> tuple[list[dict], list[dict]]:
    stmt = (
        select(User)
        .options(joinedload(User.role), joinedload(User.profile))
        .join(Role, User.role_id == Role.id)
        .where(Role.role_name.in_([ROLE_SUPPLIER, ROLE_CLIENT]))
        .order_by(User.created_at.desc())
    )
    users = list(db.scalars(stmt).unique().all())
    suppliers: list[dict] = []
    clients: list[dict] = []
    for user in users:
        company = _latest_company_for_user(db, user.id)
        item = _user_list_item(user, company)
        role_name = user.role.role_name if user.role else ""
        if role_name == ROLE_SUPPLIER:
            suppliers.append(item)
        elif role_name == ROLE_CLIENT:
            clients.append(item)
    return suppliers, clients


def get_user_detail(db: Session, user_id: int) -> User | None:
    stmt = (
        select(User)
        .options(
            joinedload(User.role),
            joinedload(User.profile),
            joinedload(User.company_memberships).joinedload(CompanyUser.company),
        )
        .where(User.id == user_id)
    )
    return db.scalar(stmt)


def count_user_orders(db: Session, user_id: int) -> int:
    """Commandes où l'utilisateur est acheteur (orders.buyer)."""
    as_buyer = int(
        db.scalar(
            select(func.count()).select_from(Order).where(Order.buyer_id == user_id)
        )
        or 0
    )
    as_seller = int(
        db.scalar(
            select(func.count())
            .select_from(ProductOrder)
            .where(ProductOrder.seller_id == user_id)
        )
        or 0
    )
    return as_buyer + as_seller


def _purge_user_dependencies(db: Session, user_id: int) -> None:
    """Retire les dépendances FK avant suppression du user (sans toucher au schéma).

    Note : les lignes product_order où il est vendeur sont retirées pour permettre
    la suppression immédiate. L'anonymisation RGPD des historiques viendra plus tard.
    """
    cart_ids = list(db.scalars(select(Cart.id).where(Cart.buyer_id == user_id)).all())
    if cart_ids:
        db.execute(delete(CartItem).where(CartItem.cart_id.in_(cart_ids)))
        db.execute(delete(Cart).where(Cart.id.in_(cart_ids)))

    order_ids = list(db.scalars(select(Order.id).where(Order.buyer_id == user_id)).all())
    if order_ids:
        db.execute(delete(Payment).where(Payment.order_id.in_(order_ids)))
        db.execute(delete(ProductOrder).where(ProductOrder.order_id.in_(order_ids)))
        db.execute(delete(Order).where(Order.id.in_(order_ids)))

    # Lignes de commande où l'utilisateur est vendeur (autres commandes)
    db.execute(delete(ProductOrder).where(ProductOrder.seller_id == user_id))

    review_ids = list(
        db.scalars(select(Review.id).where(Review.user_id == user_id)).all()
    )
    if review_ids:
        db.execute(
            delete(ReviewTranslation).where(ReviewTranslation.review_id.in_(review_ids))
        )
    db.execute(delete(Review).where(Review.user_id == user_id))
    db.execute(delete(CompanyPaymentMethod).where(CompanyPaymentMethod.user_id == user_id))
    db.execute(delete(CompanyUser).where(CompanyUser.user_id == user_id))
    db.execute(delete(EmailVerificationCode).where(EmailVerificationCode.user_id == user_id))
    db.execute(delete(UserProfile).where(UserProfile.user_id == user_id))


def delete_user(db: Session, user_id: int) -> None:
    """Supprime un utilisateur et ses données personnelles.

    Ne supprime JAMAIS la société (table ``companies``), ni ses produits.
    Seul le lien ``companies_users`` est retiré.
    """
    linked_company_tvas = list(
        db.scalars(
            select(CompanyUser.company_tva_intra_com).where(CompanyUser.user_id == user_id)
        ).all()
    )

    _purge_user_dependencies(db, user_id)
    db.execute(delete(User).where(User.id == user_id))
    db.flush()

    for tva in linked_company_tvas:
        if db.get(Company, tva) is None:
            raise RuntimeError(
                f"La société {tva} a été supprimée par erreur lors de la suppression "
                f"de l'utilisateur {user_id}."
            )


def _primary_address(db: Session, tva: str) -> Address | None:
    return db.scalar(
        select(Address)
        .where(Address.company_tva_intra_com == tva)
        .order_by(Address.is_primary.desc(), Address.id.asc())
        .limit(1)
    )


def _company_side(db: Session, tva: str) -> set[str]:
    stmt = (
        select(Role.role_name)
        .join(User, User.role_id == Role.id)
        .join(CompanyUser, CompanyUser.user_id == User.id)
        .where(CompanyUser.company_tva_intra_com == tva)
    )
    return set(db.scalars(stmt).all())


def _company_list_row(db: Session, company: Company) -> dict:
    addr = _primary_address(db, company.tva_intra_com)
    user_count = int(
        db.scalar(
            select(func.count())
            .select_from(CompanyUser)
            .where(CompanyUser.company_tva_intra_com == company.tva_intra_com)
        )
        or 0
    )
    product_count = int(
        db.scalar(
            select(func.count())
            .select_from(Product)
            .where(Product.company_tva_intra_com == company.tva_intra_com)
        )
        or 0
    )
    return {
        "tva_intra_com": company.tva_intra_com,
        "company_name": company.company_name,
        "email": company.email,
        "phone_number": company.phone_number,
        "city": addr.city if addr else None,
        "country_code": addr.country_code if addr else None,
        "user_count": user_count,
        "product_count": product_count,
        "is_verified": company.is_verified,
        "created_at": _dt_iso(company.created_at),
    }


def list_companies_by_side(db: Session) -> tuple[list[dict], list[dict]]:
    companies = list(db.scalars(select(Company).order_by(Company.company_name)).all())
    suppliers: list[dict] = []
    clients: list[dict] = []
    for company in companies:
        sides = _company_side(db, company.tva_intra_com)
        row = _company_list_row(db, company)
        if not sides:
            # Société orpheline (dernier user supprimé) — visible côté partenaires
            suppliers.append(row)
            continue
        if ROLE_SUPPLIER in sides:
            suppliers.append(row)
        if ROLE_CLIENT in sides:
            clients.append(row)
    return suppliers, clients


def get_company_detail(db: Session, tva: str) -> Company | None:
    stmt = (
        select(Company)
        .options(
            joinedload(Company.addresses),
            joinedload(Company.company_users)
            .joinedload(CompanyUser.user)
            .joinedload(User.profile),
            joinedload(Company.company_users)
            .joinedload(CompanyUser.user)
            .joinedload(User.role),
        )
        .where(Company.tva_intra_com == tva)
    )
    return db.scalar(stmt)


def count_company_products(db: Session, tva: str) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(Product).where(Product.company_tva_intra_com == tva)
        )
        or 0
    )


def count_company_shipping(db: Session, tva: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(ShippingRate)
            .where(ShippingRate.company_tva_intra_com == tva)
        )
        or 0
    )


def count_company_payments(db: Session, tva: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(CompanyPaymentMethod)
            .where(CompanyPaymentMethod.company_tva_intra_com == tva)
        )
        or 0
    )


def _delete_products_for_company(db: Session, tva: str) -> None:
    product_ids = list(
        db.scalars(select(Product.id).where(Product.company_tva_intra_com == tva)).all()
    )
    if not product_ids:
        return
    db.execute(
        update(ProductOrder)
        .where(ProductOrder.product_id.in_(product_ids))
        .values(product_id=None)
    )
    db.execute(
        delete(ProductMandatoryAttributeValue).where(
            ProductMandatoryAttributeValue.product_id.in_(product_ids)
        )
    )
    db.execute(delete(ProductAttribut).where(ProductAttribut.product_id.in_(product_ids)))
    db.execute(
        delete(ProductPriceHistory).where(ProductPriceHistory.product_id.in_(product_ids))
    )
    db.execute(delete(ProductTranslation).where(ProductTranslation.product_id.in_(product_ids)))
    db.execute(delete(CatalogProduct).where(CatalogProduct.product_id.in_(product_ids)))
    db.execute(delete(Product).where(Product.id.in_(product_ids)))


def delete_company(db: Session, tva: str) -> None:
    company = db.get(Company, tva)
    if company is None:
        raise ValueError("not_found")

    user_ids = list(
        db.scalars(
            select(CompanyUser.user_id).where(CompanyUser.company_tva_intra_com == tva)
        ).all()
    )

    _delete_products_for_company(db, tva)

    addr_ids = list(
        db.scalars(select(Address.id).where(Address.company_tva_intra_com == tva)).all()
    )
    if addr_ids:
        db.execute(
            update(Order)
            .where(Order.shipping_address_id.in_(addr_ids))
            .values(shipping_address_id=None)
        )
        db.execute(
            update(Order)
            .where(Order.invoice_address_id.in_(addr_ids))
            .values(invoice_address_id=None)
        )

    review_ids = list(
        db.scalars(select(Review.id).where(Review.company_tva_intra_com == tva)).all()
    )
    if review_ids:
        db.execute(
            delete(ReviewTranslation).where(ReviewTranslation.review_id.in_(review_ids))
        )
    db.execute(delete(Review).where(Review.company_tva_intra_com == tva))
    db.execute(delete(ShippingRate).where(ShippingRate.company_tva_intra_com == tva))
    db.execute(delete(CompanyBankInfo).where(CompanyBankInfo.company_tva_intra_com == tva))
    db.execute(
        delete(CompanyPaymentMethod).where(CompanyPaymentMethod.company_tva_intra_com == tva)
    )
    db.execute(delete(Address).where(Address.company_tva_intra_com == tva))
    db.execute(delete(CompanyUser).where(CompanyUser.company_tva_intra_com == tva))

    for uid in user_ids:
        if db.get(User, uid) is None:
            continue
        _purge_user_dependencies(db, uid)
        db.execute(delete(User).where(User.id == uid))

    db.execute(delete(Company).where(Company.tva_intra_com == tva))
    db.flush()
