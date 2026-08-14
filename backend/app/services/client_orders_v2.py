from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Product
from app.repositories import client_orders_v2_repo, product_price_repo
from app.repositories import suppliers_offers_v2_repo
from app.schemas.client_orders_v2 import (
    ClientCheckoutCreateV2,
    ClientCheckoutCreatedV2,
    ClientCheckoutOrderPartV2,
)


@dataclass
class ClientOrderV2Error(Exception):
    field: str
    message: str


def _money(x: float | Decimal) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"))


def checkout_client_v2(
    db: Session,
    payload: ClientCheckoutCreateV2,
) -> ClientCheckoutCreatedV2:
    buyer = client_orders_v2_repo.get_user(db=db, user_id=payload.buyer_id)
    if buyer is None:
        raise ClientOrderV2Error(field="buyer_id", message="Acheteur introuvable.")
    buyer_role = client_orders_v2_repo.get_role_name(db=db, role_id=buyer.role_id)
    if buyer_role != client_orders_v2_repo.ROLE_CLIENT:
        raise ClientOrderV2Error(
            field="buyer_id",
            message="L'utilisateur acheteur doit avoir le role Client.",
        )

    line_details: list[tuple[str, Product, Decimal, int]] = []

    for line in payload.items:
        product = client_orders_v2_repo.get_product(db=db, product_id=line.product_id)
        if product is None:
            raise ClientOrderV2Error(
                field="items",
                message=f"Produit introuvable: {line.product_id}",
            )
        if not product.is_active:
            raise ClientOrderV2Error(
                field="items",
                message=f"Produit inactif: {line.product_id}",
            )

        latest = product_price_repo.get_latest_price(db, product.id)
        if latest is None:
            raise ClientOrderV2Error(
                field="items",
                message=f"Aucun prix enregistré pour le produit {line.product_id}.",
            )
        if str(latest.currency).upper() != payload.currency.upper():
            raise ClientOrderV2Error(
                field="currency",
                message=(
                    f"Devise produit ({latest.currency}) incompatible avec "
                    f"currency commande ({payload.currency}) pour produit {line.product_id}."
                ),
            )
        if payload.decrement_stock:
            pass  # stock retiré du modèle produit (Patch v2)

        unit_price = _money(latest.price)
        line_details.append((product.company_tva_intra_com, product, unit_price, line.quantity))

    groups: dict[str, list[tuple[Product, Decimal, int]]] = defaultdict(list)
    for company_tva, product, unit_price, qty in line_details:
        groups[company_tva].append((product, unit_price, qty))

    cart_subtotal = Decimal("0")
    for _tva, _p, unit_price, qty in line_details:
        cart_subtotal += unit_price * qty

    tax_total = _money(payload.tax_amount)
    # v1 : frais de livraison exclus du checkout (module buyer_shipping conservé)
    ship_total = Decimal("0.00")
    currency = payload.currency.upper()

    order_parts: list[ClientCheckoutOrderPartV2] = []

    for company_tva, group_lines in groups.items():
        group_subtotal = sum(up * q for _p, up, q in group_lines)

        if cart_subtotal > 0:
            ratio = group_subtotal / cart_subtotal
        else:
            ratio = Decimal("0")
        group_tax = (tax_total * ratio).quantize(Decimal("0.01"))
        group_ship = (ship_total * ratio).quantize(Decimal("0.01"))
        order_total = group_subtotal + group_tax + group_ship

        order = client_orders_v2_repo.create_order(
            db=db,
            buyer_id=payload.buyer_id,
            status=payload.status,
            subtotal=group_subtotal,
            tax_amount=group_tax,
            shipping_amount=group_ship,
            total_amount=order_total,
            currency=currency,
            shipping_address_id=payload.shipping_address_id,
            invoice_address_id=payload.invoice_address_id,
        )

        line_subtotals = [up * q for _p, up, q in group_lines]
        sum_g = sum(line_subtotals) if line_subtotals else Decimal("0")

        po_ids: list[int] = []
        for idx, (product, unit_price, qty) in enumerate(group_lines):
            if sum_g > 0:
                share = (line_subtotals[idx] / sum_g) * group_ship
            else:
                share = group_ship if idx == 0 else Decimal("0")
            share = share.quantize(Decimal("0.01"))
            line_total = unit_price * qty + share

            catalog_id = suppliers_offers_v2_repo.get_product_primary_catalog_id(
                db, product.id
            )
            if catalog_id is None:
                raise ClientOrderV2Error(
                    field="items",
                    message=f"Produit {line.product_id} sans catalogue associé.",
                )
            po = client_orders_v2_repo.create_product_order(
                db=db,
                order_id=order.id,
                catalog_id=catalog_id,
                product_id=product.id,
                quantity=qty,
                unit_price=unit_price,
                shipping_cost=share,
                total_price=line_total,
            )
            po_ids.append(po.id)

            if payload.decrement_stock:
                client_orders_v2_repo.decrement_product_stock(db=db, product=product, qty=qty)
        order_parts.append(
            ClientCheckoutOrderPartV2(
                order_id=order.id,
                company_id=company_tva,
                subtotal=float(group_subtotal),
                tax_amount=float(group_tax),
                shipping_amount=float(group_ship),
                total_amount=float(order_total),
                product_order_ids=po_ids,
            )
        )

    db.commit()

    return ClientCheckoutCreatedV2(
        buyer_id=payload.buyer_id,
        currency=currency,
        orders=order_parts,
    )
