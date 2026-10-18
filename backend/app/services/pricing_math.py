"""Formules de livraison et de remise, sans accès base.

Massif : 26 t / camion (+ 5 %), (2/0,75) €/km par camion + 3,4 €/t,
puis max(300/0,75 €, ce prix) par groupe.
Totem : 6 / camion, max(600 €, n × (250 € + 1 €/km)) par groupe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

MASSIF_TRUCK_CAPACITY_KG = 26_000
MASSIF_TRUCK_TOLERANCE = Decimal("1.05")
MASSIF_PER_KM_EUR = Decimal("2") / Decimal("0.75")
MASSIF_PER_TON_EUR = Decimal("3.4")
MASSIF_SHIPPING_MIN_EUR = Decimal("300") / Decimal("0.75")

TOTEM_TRUCK_CAPACITY = 6
TOTEM_TRUCK_BASE_EUR = Decimal("250")
TOTEM_PER_KM_EUR = Decimal("1")
TOTEM_SHIPPING_MIN_EUR = Decimal("600")

PANEL_EUR_PER_M2 = Decimal("100")


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def effective_unit_price(price: Decimal, marge: Decimal, abonne: bool) -> Decimal:
    if abonne:
        return money(price)
    return money(price * marge)


def totem_discount_rate(qty: int) -> Decimal:
    if qty >= 10:
        return Decimal("0.15")
    if qty >= 5:
        return Decimal("0.10")
    return Decimal("0")


def panel_print_price(length_cm: Decimal, height_cm: Decimal) -> Decimal:
    return money((length_cm / Decimal("100")) * (height_cm / Decimal("100")) * PANEL_EUR_PER_M2)


def palettes_needed(qty: int, per_palette: int) -> int:
    if qty <= 0 or per_palette <= 0:
        return 0
    return math.ceil(qty / per_palette)


def massif_handling_units(qty: int, per_palette: int) -> int:
    """Palettes à manipuler, ou massifs à l'unité s'ils ne sont pas palettisés."""
    if qty <= 0:
        return 0
    if per_palette > 0:
        return palettes_needed(qty, per_palette)
    return qty


def massif_trucks(total_weight_kg: Decimal) -> int:
    weight = Decimal(total_weight_kg)
    if weight <= 0:
        return 0
    if weight <= MASSIF_TRUCK_CAPACITY_KG * MASSIF_TRUCK_TOLERANCE:
        return 1
    return math.ceil(weight / MASSIF_TRUCK_CAPACITY_KG)


def massif_truck_cost(total_weight_kg: Decimal, distance_km: Decimal, trucks: int) -> Decimal:
    if trucks <= 0:
        return Decimal("0")
    distance_fee = MASSIF_PER_KM_EUR * trucks * distance_km
    tonnage_fee = (total_weight_kg / Decimal("1000")) * MASSIF_PER_TON_EUR
    return money(max(MASSIF_SHIPPING_MIN_EUR, distance_fee + tonnage_fee))


def totem_trucks(qty: int) -> int:
    if qty <= 0:
        return 0
    return math.ceil(qty / TOTEM_TRUCK_CAPACITY)


def totem_truck_cost(qty: int, distance_km: Decimal) -> Decimal:
    trucks = totem_trucks(qty)
    if trucks <= 0:
        return Decimal("0")
    raw = trucks * (TOTEM_TRUCK_BASE_EUR + TOTEM_PER_KM_EUR * distance_km)
    return money(max(TOTEM_SHIPPING_MIN_EUR, raw))


@dataclass(frozen=True)
class TruckGroupKey:
    supplier_tva: str
    address_id: int
