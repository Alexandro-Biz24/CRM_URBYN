from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload, selectinload

from decimal import Decimal

from app.models import ClientOrder, ClientOrderItem, Company, Product, User
from app.repositories import supplier_offers_repo as offers_repo
from app.services.pricing import URBANIZE_TVA, CartLineIn, QuoteContext, quote_lines
from app.services.pricing_math import effective_unit_price
from app.repositories import supplier_portal_repo as supplier_repo
from app.schemas.client_orders import (
    ClientOrderCardOut,
    ClientOrderCreate,
    ClientOrderDetailOut,
    ClientOrderItemOut,
    ClientOrderListOut,
    SupplierLeadCardOut,
    SupplierLeadDetailOut,
    SupplierLeadListOut,
)
from app.schemas.supplier_portal import PortalSession
from app.services.client_portal import ClientPortalError
from app.services.supplier_portal import PortalError as SupplierPortalError
from app.services.supplier_portal import get_context as get_supplier_context


def _require_client_user(db: Session, session: PortalSession) -> User:
    user = supplier_repo.get_user(db, session.user_id, str(session.email))
    if user is None:
        raise ClientPortalError("session_mismatch", "Session invalide.")
    if user.role is None or user.role.role_name != "Client":
        raise ClientPortalError("role_mismatch", "Accès réservé aux clients.")
    return user


def _item_supplier(details: dict[str, Any] | None) -> tuple[str | None, str | None]:
    d = details or {}
    tva = (
        d.get("companyTva")
        or d.get("company_tva")
        or d.get("supplierTva")
        or d.get("supplier_tva")
    )
    name = (
        d.get("companyName")
        or d.get("company_name")
        or d.get("supplierName")
        or d.get("supplier_name")
    )
    tva_s = str(tva).strip() if tva else None
    name_s = str(name).strip() if name else None
    return tva_s or None, name_s or None


def _item_type(item) -> str:
    details = item.details or {}
    return str(details.get("itemType") or item.type or "product")


def _product_id(item) -> int | None:
    details = item.details or {}
    raw = details.get("productId") or details.get("product_id")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _resolve_supplier(
    db: Session, details: dict[str, Any], product_id: int | None
) -> tuple[str | None, str | None]:
    tva, name = _item_supplier(details)
    if tva and name:
        return tva, name
    if product_id is None:
        return tva, name
    product = db.get(Product, product_id)
    if product is None:
        return tva, name
    if not tva:
        tva = product.company_tva_intra_com
    if not name and tva:
        company = db.get(Company, tva)
        name = company.company_name if company else None
    return tva, name


def _frozen_unit(db: Session, product_id: int | None, supplier_tva: str | None, fallback: float) -> float:
    if product_id is None or not supplier_tva:
        return round(fallback, 2)
    offer = offers_repo.latest_offer(db, supplier_tva, product_id)
    if offer is None:
        return round(fallback, 2)
    sub = offers_repo.get_subscription(db, supplier_tva)
    unit = effective_unit_price(
        Decimal(str(offer.price)),
        Decimal(str(offer.urbyn_marge)),
        bool(sub and sub.abonne),
    )
    return float(unit)


def _quote_for_order(db: Session, payload: ClientOrderCreate, lines: list[CartLineIn]) -> dict:
    address = payload.deliveryAddress
    ctx = QuoteContext(
        postal_code=(address.postalCode if address and address.postalCode else "") or "",
        city=(address.city if address and address.city else "") or "",
        country="FR",
        massif_transport=payload.massifTransport,
        massif_dechargement=payload.massifDechargement,
        massif_installation=payload.massifInstallation,
        totem_transport=payload.totemTransport,
        totem_installation=payload.totemInstallation,
    )
    if not lines:
        return {
            "shipping": 0.0,
            "dechargement": 0.0,
            "installation": 0.0,
            "totem_installation": 0.0,
            "discount": 0.0,
            "shipping_by_supplier": {},
            "discount_by_supplier": {},
        }
    return quote_lines(db, lines, ctx)


def create_client_order(db: Session, payload: ClientOrderCreate) -> ClientOrderDetailOut:
    user = _require_client_user(db, payload.session)

    items_in = [i for i in payload.items if i.quantity > 0]
    if not items_in:
        raise ClientPortalError("empty_order", "Aucun article à enregistrer.")

    priced: list[dict[str, Any]] = []
    quote_lines_in: list[CartLineIn] = []
    for item in items_in:
        details = dict(item.details or {})
        pid = _product_id(item)
        tva, supplier_name = _resolve_supplier(db, details, pid)
        item_type = _item_type(item)
        qty = max(1, int(item.quantity))
        if item_type != "panels" and pid and tva:
            quote_lines_in.append(CartLineIn(pid, tva, qty))
        unit = _frozen_unit(db, pid, tva, float(item.price))
        if tva and "companyTva" not in details:
            details["companyTva"] = tva
        if supplier_name and "companyName" not in details:
            details["companyName"] = supplier_name
        priced.append(
            {
                "product_id": pid,
                "item_type": item_type,
                "name": (item.name or "Produit").strip()[:512],
                "quantity": qty,
                "unit": unit,
                "line": round(unit * qty, 2),
                "tva": tva,
                "supplier_name": supplier_name,
                "details": details or None,
            }
        )

    quoted = _quote_for_order(db, payload, quote_lines_in)
    subtotal = round(sum(row["line"] for row in priced), 2)
    discount = round(float(quoted.get("discount") or 0), 2)
    shipping = round(float(quoted.get("shipping") or 0), 2)
    services = round(
        float(quoted.get("dechargement") or 0)
        + float(quoted.get("installation") or 0)
        + float(quoted.get("totem_installation") or 0),
        2,
    )
    total_ht = round(subtotal - discount + shipping + services, 2)
    tax = round(total_ht * 0.2, 2)
    total_ttc = round(total_ht * 1.2, 2)

    delivery = payload.deliveryAddress.model_dump() if payload.deliveryAddress else None
    breakdown = {
        "by_supplier": quoted.get("shipping_by_supplier") or {},
        "discount_by_supplier": quoted.get("discount_by_supplier") or {},
        "dechargement": float(quoted.get("dechargement") or 0),
        "installation": float(quoted.get("installation") or 0),
        "totem_installation": float(quoted.get("totem_installation") or 0),
        "discount": discount,
    }

    order = ClientOrder(
        buyer_user_id=user.id,
        status="submitted",
        contact_first_name=payload.contact.firstName or None,
        contact_last_name=payload.contact.lastName or None,
        contact_email=payload.contact.email or user.email,
        contact_phone=payload.contact.phone or None,
        delivery_address=delivery,
        shipping_breakdown=breakdown,
        subtotal_ht=round(subtotal - discount, 2),
        shipping_amount=shipping,
        install_amount=services,
        tax_amount=tax,
        total_ht=total_ht,
        total_ttc=total_ttc,
        currency="EUR",
        notes=payload.notes,
    )
    db.add(order)
    db.flush()

    for row in priced:
        db.add(
            ClientOrderItem(
                order_id=order.id,
                product_id=row["product_id"],
                item_type=row["item_type"],
                name=row["name"],
                quantity=row["quantity"],
                unit_price_ht=row["unit"],
                line_total_ht=row["line"],
                supplier_company_tva=row["tva"],
                supplier_name=row["supplier_name"],
                details=row["details"],
            )
        )

    db.commit()
    return get_buyer_order_detail(db, payload.session, order.id)


def _order_card(order: ClientOrder) -> ClientOrderCardOut:
    suppliers = sorted(
        {
            (it.supplier_name or it.supplier_company_tva or "").strip()
            for it in order.items
            if (it.supplier_name or it.supplier_company_tva)
        }
    )
    city = None
    if isinstance(order.delivery_address, dict):
        city = order.delivery_address.get("city")
    return ClientOrderCardOut(
        id=order.id,
        status=order.status,
        created_at=order.created_at,
        total_ht=float(order.total_ht),
        total_ttc=float(order.total_ttc),
        currency=order.currency,
        items_count=len(order.items),
        suppliers=suppliers,
        delivery_city=city,
        preview_names=[it.name for it in order.items[:3]],
    )


def _item_out(it: ClientOrderItem) -> ClientOrderItemOut:
    line_ht = float(it.line_total_ht)
    return ClientOrderItemOut(
        id=it.id,
        product_id=it.product_id,
        item_type=it.item_type,
        name=it.name,
        quantity=it.quantity,
        unit_price_ht=float(it.unit_price_ht),
        line_total_ht=line_ht,
        line_total_ttc=round(line_ht * 1.2, 2),
        supplier_company_tva=it.supplier_company_tva,
        supplier_name=it.supplier_name,
        details=it.details,
    )


def list_buyer_orders(db: Session, session: PortalSession) -> ClientOrderListOut:
    user = _require_client_user(db, session)
    rows = db.scalars(
        select(ClientOrder)
        .options(selectinload(ClientOrder.items))
        .where(ClientOrder.buyer_user_id == user.id)
        .order_by(desc(ClientOrder.created_at))
    ).all()
    return ClientOrderListOut(count=len(rows), orders=[_order_card(o) for o in rows])


def get_buyer_order_detail(
    db: Session, session: PortalSession, order_id: int
) -> ClientOrderDetailOut:
    user = _require_client_user(db, session)
    order = db.scalar(
        select(ClientOrder)
        .options(selectinload(ClientOrder.items))
        .where(ClientOrder.id == order_id, ClientOrder.buyer_user_id == user.id)
    )
    if order is None:
        raise ClientPortalError("not_found", "Commande introuvable.")
    suppliers = sorted(
        {
            (it.supplier_name or it.supplier_company_tva or "").strip()
            for it in order.items
            if (it.supplier_name or it.supplier_company_tva)
        }
    )
    return ClientOrderDetailOut(
        id=order.id,
        status=order.status,
        created_at=order.created_at,
        updated_at=order.updated_at,
        contact_first_name=order.contact_first_name,
        contact_last_name=order.contact_last_name,
        contact_email=order.contact_email,
        contact_phone=order.contact_phone,
        delivery_address=order.delivery_address,
        shipping_breakdown=order.shipping_breakdown,
        subtotal_ht=float(order.subtotal_ht),
        shipping_amount=float(order.shipping_amount),
        install_amount=float(order.install_amount),
        tax_amount=float(order.tax_amount),
        total_ht=float(order.total_ht),
        total_ttc=float(order.total_ttc),
        currency=order.currency,
        notes=order.notes,
        items=[_item_out(it) for it in order.items],
        suppliers=suppliers,
    )


def _supplier_amounts(order: ClientOrder, tva: str) -> tuple[list[ClientOrderItem], float, float, float, float]:
    mine = [it for it in order.items if it.supplier_company_tva == tva]
    sub = round(sum(float(it.line_total_ht) for it in mine), 2)
    breakdown = order.shipping_breakdown if isinstance(order.shipping_breakdown, dict) else {}
    shipping = round(float((breakdown.get("by_supplier") or {}).get(tva) or 0), 2)
    discount = round(float((breakdown.get("discount_by_supplier") or {}).get(tva) or 0), 2)
    services = 0.0
    if tva == URBANIZE_TVA:
        services = round(
            float(breakdown.get("dechargement") or 0)
            + float(breakdown.get("installation") or 0)
            + float(breakdown.get("totem_installation") or 0),
            2,
        )
    total = round(sub - discount + shipping + services, 2)
    return mine, sub, shipping, services, total


def list_supplier_leads(db: Session, session: PortalSession) -> SupplierLeadListOut:
    portal = get_supplier_context(db, session)
    tva = portal.company_id
    order_ids = db.scalars(
        select(ClientOrderItem.order_id)
        .where(ClientOrderItem.supplier_company_tva == tva)
        .distinct()
    ).all()
    if not order_ids:
        return SupplierLeadListOut(count=0, leads=[])

    orders = db.scalars(
        select(ClientOrder)
        .options(
            selectinload(ClientOrder.items),
            joinedload(ClientOrder.buyer).joinedload(User.profile),
        )
        .where(ClientOrder.id.in_(list(order_ids)))
        .order_by(desc(ClientOrder.created_at))
    ).all()

    leads: list[SupplierLeadCardOut] = []
    for order in orders:
        mine, sub, shipping, _services, total = _supplier_amounts(order, tva)
        if not mine:
            continue
        buyer_label = None
        if order.contact_first_name or order.contact_last_name:
            buyer_label = " ".join(
                x for x in [order.contact_first_name, order.contact_last_name] if x
            ).strip()
        city = None
        if isinstance(order.delivery_address, dict):
            city = order.delivery_address.get("city")
        leads.append(
            SupplierLeadCardOut(
                order_id=order.id,
                status=order.status,
                created_at=order.created_at,
                buyer_label=buyer_label or order.contact_email,
                delivery_city=city,
                items_count=len(mine),
                supplier_shipping_ht=shipping,
                supplier_total_ht=total,
                supplier_total_ttc=round(total * 1.2, 2),
                currency=order.currency,
                preview_names=[it.name for it in mine[:3]],
            )
        )
    return SupplierLeadListOut(count=len(leads), leads=leads)


def get_supplier_lead_detail(
    db: Session, session: PortalSession, order_id: int
) -> SupplierLeadDetailOut:
    portal = get_supplier_context(db, session)
    tva = portal.company_id
    order = db.scalar(
        select(ClientOrder)
        .options(selectinload(ClientOrder.items))
        .where(ClientOrder.id == order_id)
    )
    if order is None:
        raise SupplierPortalError("not_found", "Lead introuvable.")
    mine, sub, shipping, services, total = _supplier_amounts(order, tva)
    if not mine:
        raise SupplierPortalError(
            "not_found", "Aucun produit de votre société sur cette commande."
        )
    buyer_label = None
    if order.contact_first_name or order.contact_last_name:
        buyer_label = " ".join(
            x for x in [order.contact_first_name, order.contact_last_name] if x
        ).strip()
    return SupplierLeadDetailOut(
        order_id=order.id,
        status=order.status,
        created_at=order.created_at,
        buyer_label=buyer_label or order.contact_email,
        contact_email=order.contact_email,
        contact_phone=order.contact_phone,
        delivery_address=order.delivery_address,
        currency=order.currency,
        supplier_subtotal_ht=sub,
        supplier_shipping_ht=shipping,
        supplier_services_ht=services,
        supplier_total_ht=total,
        supplier_total_ttc=round(total * 1.2, 2),
        items=[_item_out(it) for it in mine],
    )
