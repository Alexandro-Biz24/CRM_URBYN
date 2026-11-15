"""Formules de livraison et de remise, sans accès base.

Massif livraison : 26 t / camion (+ 5 %), max(600 €, camions × 2,6 €/km),
puis arrondi à la dizaine supérieure.
Surcharge énergie : 3,4 € × tonnes de la commande, arrondies à la tonne supérieure.
Totem : 6 / camion, max(600 €, n × (250 € + 1 €/km)) par groupe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

MASSIF_TRUCK_CAPACITY_KG = 26_000
MASSIF_TRUCK_TOLERANCE = Decimal("1.05")
MASSIF_PER_KM_EUR = Decimal("2.6")
MASSIF_PER_TON_EUR = Decimal("3.4")
MASSIF_SHIPPING_MIN_EUR = Decimal("600")

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


def massif_billed_tons(total_weight_kg: Decimal) -> Decimal:
    """Poids de la commande arrondi à la tonne supérieure."""
    if total_weight_kg <= 0:
        return Decimal("0")
    return (total_weight_kg / Decimal("1000")).quantize(Decimal("1"), rounding=ROUND_CEILING)


def massif_energy_surcharge(total_weight_kg: Decimal) -> Decimal:
    tons = massif_billed_tons(total_weight_kg)
    if tons <= 0:
        return Decimal("0")
    return money(tons * MASSIF_PER_TON_EUR)


def round_up_to_ten(value: Decimal) -> Decimal:
    """Arrondi à la dizaine d'euros supérieure. Un multiple de 10 reste tel quel."""
    if value <= 0:
        return Decimal("0")
    return (value / Decimal("10")).quantize(Decimal("1"), rounding=ROUND_CEILING) * Decimal("10")


def massif_truck_cost(total_weight_kg: Decimal, distance_km: Decimal, trucks: int) -> Decimal:
    if trucks <= 0:
        return Decimal("0")
    distance_fee = MASSIF_PER_KM_EUR * trucks * distance_km
    return round_up_to_ten(max(MASSIF_SHIPPING_MIN_EUR, distance_fee))


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
